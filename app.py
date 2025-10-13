import os
import sys
import shutil
import pandas as pd
from datetime import datetime
from flask import Flask, jsonify, request, render_template, session, redirect, url_for, flash, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image
import uuid
from functools import wraps
class DrinkApp:
    def __init__(self, reset):
        self.app = Flask(__name__)
        self.app.secret_key = 'your_secret_key_change_in_production'


        self.app_state_file = "./app_state.txt"
        self.app_running = self.load_app_state()

        self.archives = "./archives"
        self.database = "./database"
        self.drink_db = os.path.join(self.database, "drink_db.csv")
        self.user_db = os.path.join(self.database, "user_db.csv")
        self.team_db = os.path.join(self.database, "team_db.csv")
        self.total_drinks = "total_drinks.csv"
        
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.pictures = os.path.join(base_dir, "pictures")
        self.thumbnails = os.path.join(base_dir, "thumbnails")
        self.app.config['UPLOAD_FOLDER'] = self.pictures
        
        print(f"🗂️ Pictures directory: {self.pictures}")
        print(f"🗂️ Thumbnails directory: {self.thumbnails}")
        print(f"🗂️ Running from: {base_dir}")
        print(f"🗂️ Frozen: {getattr(sys, 'frozen', False)}")
        print("🔥 LATEST VERSION WITH DEBUG LOADED! 🔥")
        self.allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
        self.admin_password = "test741"

        os.makedirs(self.database, exist_ok=True)
        os.makedirs(self.pictures, exist_ok=True)
        os.makedirs(self.thumbnails, exist_ok=True)
        os.makedirs(self.archives, exist_ok=True)
        if reset or not os.path.exists(self.drink_db) or not os.path.exists(self.user_db) or not os.path.exists(self.team_db):
            self.initialization()

        self.add_routes()

    def admin_required(self, f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'admin_logged_in' not in session or not session['admin_logged_in']:
                return redirect(url_for('admin_login'))
            return f(*args, **kwargs)
        return decorated_function

    def load_app_state(self):
        try:
            if os.path.exists(self.app_state_file):
                with open(self.app_state_file, 'r') as f:
                    state = f.read().strip().lower()
                    return state == 'running'
            return True
        except Exception as e:
            print(f"Error loading app state: {e}")
            return True

    def save_app_state(self, running=True):
        try:
            with open(self.app_state_file, 'w') as f:
                f.write('running' if running else 'stopped')
            self.app_running = running
            return True
        except Exception as e:
            print(f"Error saving app state: {e}")
            return False

    def start_application(self):
        return self.save_app_state(True)

    def stop_application(self):
        return self.save_app_state(False)

    def restart_application(self):
        self.stop_application()
        return self.start_application()

    def is_app_running(self):
        return self.app_running

    def validate_user_from_cookie(self, user_id):
        if not user_id:
            return False
        
        try:
            user_data = self.load_data_from_csv(self.user_db)
            if user_data.empty:
                return False
            
            user_exists = user_id in user_data['id'].values
            return user_exists
        except Exception as e:
            print(f"Error validating user from cookie: {e}")
            return False

    def initialization(self):
        if not os.path.exists(self.drink_db):
            pd.DataFrame(columns=['id','username', 'team', 'timestamp', 'count']).to_csv(self.drink_db, index=False)
        
        if not os.path.exists(self.user_db):
            pd.DataFrame(columns=['id','username', 'color', 'team']).to_csv(self.user_db, index=False)
        
        if not os.path.exists(self.team_db):
            pd.DataFrame(columns=['team', 'color']).to_csv(self.team_db, index=False)
        current_date = datetime.now().strftime('%Y_%m_%d')
        sik_folder = os.path.join(self.archives, f"sik_{current_date}")
        os.makedirs(sik_folder, exist_ok=True)

        if os.path.exists(self.drink_db):
            archived_db_path = os.path.join(sik_folder, "drink_db.csv")
            shutil.move(self.drink_db, archived_db_path)

            if os.path.exists(self.total_drinks):
                total_drinks_df = pd.read_csv(self.total_drinks)
            else:
                total_drinks_df = pd.DataFrame(columns=['id','username', 'team', 'timestamp', 'count'])

            archived_df = pd.read_csv(archived_db_path)
            total_drinks_df = pd.concat([total_drinks_df, archived_df], ignore_index=True)
            total_drinks_df.to_csv(self.total_drinks, index=False)

        pd.DataFrame(columns=['id','username', 'team', 'timestamp', 'count']).to_csv(self.drink_db, index=False)
        pd.DataFrame(columns=['id','username', 'color', 'team']).to_csv(self.user_db, index=False)
        df = pd.DataFrame(columns=['team', 'color'])
        df.to_csv(self.team_db, mode='w', header=True, index=False)

        sik_pictures_folder = os.path.join(sik_folder, "pictures")
        os.makedirs(sik_pictures_folder, exist_ok=True)
        for filename in os.listdir(self.pictures):
            file_path = os.path.join(self.pictures, filename)
            if os.path.isfile(file_path) and filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                shutil.move(file_path, os.path.join(sik_pictures_folder, filename))

        for filename in os.listdir(self.pictures):
            file_path = os.path.join(self.pictures, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"Erreur lors de la suppression de {file_path} : {e}")

    def allowed_file(self, filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in self.allowed_extensions

    def save_drink_to_csv(self,user_id, username, team, timestamp, vomit=False):
        if vomit:
            new_entry = pd.DataFrame([[user_id, username, team, timestamp, -1]], columns=['id','username', 'team', 'timestamp', 'count'])
        else:
            new_entry = pd.DataFrame([[user_id, username, team, timestamp, 1]], columns=['id','username', 'team', 'timestamp', 'count'])
        new_entry.to_csv(self.drink_db, mode='a', header=False, index=False)

    def load_data_from_csv(self, csv_file):
        if os.path.exists(csv_file):
            return pd.read_csv(csv_file)
        

    def get_beers_data(self):
        drinks = self.load_data_from_csv(self.drink_db)
        drinks = drinks.sort_values(by=['timestamp'])
        last_beer_count = {}
        processed_data = []
        for _, row in drinks.iterrows():
            user_id = row['id']
            count = row['count']
            
            if count == 1:
                if user_id not in last_beer_count:
                    last_beer_count[user_id] = 0
                last_beer_count[user_id] += 1
                processed_row = row.copy()
                processed_row['cumulative_count'] = last_beer_count[user_id]
                processed_data.append(processed_row)
                
            elif count == -1:
                if user_id in last_beer_count:
                    processed_row = row.copy()
                    processed_row['cumulative_count'] = last_beer_count[user_id]
                    processed_data.append(processed_row)
                else:
                    processed_row = row.copy()
                    processed_row['cumulative_count'] = 0
                    processed_data.append(processed_row)
        result = pd.DataFrame(processed_data)
        
        return result
    

    def get_top_10_users(self):
        drinks = self.load_data_from_csv(self.drink_db)
        beers = drinks[drinks['count'] == 1]
        top_users = beers.groupby(['id', 'username', 'team'], as_index=False)['count'].sum()
        top_10 = top_users.nlargest(10, 'count').reset_index(drop=True)
        
        return top_10.to_dict(orient='records')

    def get_team_data(self):
        drinks = self.load_data_from_csv(self.drink_db)
        teams = self.load_data_from_csv(self.team_db)

        beers = drinks[drinks['count'] == 1]
        vomits = drinks[drinks['count'] == -1]

        beer_counts = beers.groupby('team')['count'].sum().reset_index()
        beer_counts = beer_counts.rename(columns={'count': 'beer_count'})
        vomit_counts = vomits.groupby('team').size().reset_index(name='vomit_count')
        team_data = pd.merge(beer_counts, vomit_counts, on='team', how='outer').fillna(0)
        team_data['beer_count'] = team_data['beer_count'].astype(int)
        team_data['vomit_count'] = team_data['vomit_count'].astype(int)
        merged_data = pd.merge(team_data, teams, on='team', how='left')

        merged_data = merged_data.rename(columns={'color': 'team_color'})

        return merged_data.to_dict(orient='records')

    def get_team_list(self):
        data = self.load_data_from_csv(self.team_db)
        teams = data.set_index('team')['color'].to_dict()
        return teams


    def get_user_list(self):
        data = self.load_data_from_csv(self.user_db)
        teams = data.set_index('id')[['username', 'color']].to_dict(orient='index')
        return teams

    def get_user_info(self, user_id):
        user_data = self.load_data_from_csv(self.user_db)
        team_data = self.load_data_from_csv(self.team_db)

        drink_data = self.load_data_from_csv(self.drink_db)
        user_info = user_data[user_data['id'].str.lower() == user_id.lower()]

        if user_info.empty:
            return {}

        merged_data = pd.merge(user_info, team_data, on='team', how='left', suffixes=('', '_team'))
        user_drink_data = drink_data[(drink_data['id'].str.lower() == user_id.lower())]
        drink_count = user_drink_data[user_drink_data['count'] == 1]['count'].count()
        vomit_count = user_drink_data[user_drink_data['count'] == -1]['count'].count()
        merged_data['drink_count'] = drink_count
        merged_data['vomit_count'] = vomit_count
        merged_data = merged_data.rename(columns={'color_team': 'team_color', 'drink_count':'drink_count', 'vomit_count':'vomit_count'})
        print(merged_data)
        result = merged_data[['id', 'username', 'color', 'team', 'team_color', 'drink_count','vomit_count']]

        return result.to_dict(orient='records')

    def get_all_users(self):
        """Get all users with their team information"""
        user_data = self.load_data_from_csv(self.user_db)
        team_data = self.load_data_from_csv(self.team_db)
        drink_data = self.load_data_from_csv(self.drink_db)
        
        if user_data.empty:
            return []
        
        merged_data = pd.merge(user_data, team_data, on='team', how='left', suffixes=('', '_team'))
        
        result = []
        for _, user in merged_data.iterrows():
            user_drinks = drink_data[drink_data['id'] == user['id']]
            drink_count = user_drinks[user_drinks['count'] == 1]['count'].sum()
            vomit_count = user_drinks[user_drinks['count'] == -1]['count'].count()
            
            user_info = {
                'id': user['id'],
                'username': user['username'],
                'color': user['color'],
                'team': user['team'],
                'team_color': user['color_team'] if pd.notna(user['color_team']) else '#000000',
                'drink_count': int(drink_count) if pd.notna(drink_count) else 0,
                'vomit_count': int(vomit_count) if pd.notna(vomit_count) else 0
            }
            result.append(user_info)
        
        return result

    def get_all_teams(self):
        team_data = self.load_data_from_csv(self.team_db)
        user_data = self.load_data_from_csv(self.user_db)
        drink_data = self.load_data_from_csv(self.drink_db)
        
        if team_data.empty:
            return []
        
        result = []
        for _, team in team_data.iterrows():
            team_users = user_data[user_data['team'] == team['team']]
            team_drinks = drink_data[drink_data['team'] == team['team']]
            
            beer_count = team_drinks[team_drinks['count'] == 1]['count'].sum()
            vomit_count = team_drinks[team_drinks['count'] == -1]['count'].count()
            
            team_info = {
                'team': team['team'],
                'color': team['color'],
                'user_count': len(team_users),
                'beer_count': int(beer_count) if pd.notna(beer_count) else 0,
                'vomit_count': int(vomit_count) if pd.notna(vomit_count) else 0
            }
            result.append(team_info)
        
        return result

    def get_user_drinks(self, user_id):
        drink_data = self.load_data_from_csv(self.drink_db)
        user_drinks = drink_data[drink_data['id'] == user_id].copy()
        
        if user_drinks.empty:
            return []
        
        user_drinks = user_drinks.sort_values(by='timestamp', ascending=False)
        return user_drinks.to_dict(orient='records')

    def delete_user(self, user_id):
        try:
            user_data = self.load_data_from_csv(self.user_db)
            user_data = user_data[user_data['id'] != user_id]
            user_data.to_csv(self.user_db, index=False)
            
            drink_data = self.load_data_from_csv(self.drink_db)
            drink_data = drink_data[drink_data['id'] != user_id]
            drink_data.to_csv(self.drink_db, index=False)
            
            return True
        except Exception as e:
            print(f"Error deleting user: {e}")
            return False

    def delete_team(self, team_name):
        try:
            user_data = self.load_data_from_csv(self.user_db)
            user_data.loc[user_data['team'] == team_name, 'team'] = 'No Team'
            user_data.to_csv(self.user_db, index=False)
            
            drink_data = self.load_data_from_csv(self.drink_db)
            drink_data.loc[drink_data['team'] == team_name, 'team'] = 'No Team'
            drink_data.to_csv(self.drink_db, index=False)
            
            team_data = self.load_data_from_csv(self.team_db)
            team_data = team_data[team_data['team'] != team_name]
            team_data.to_csv(self.team_db, index=False)
            
            return True
        except Exception as e:
            print(f"Error deleting team: {e}")
            return False

    def update_user(self, user_id, username, color, team):
        try:
            user_data = self.load_data_from_csv(self.user_db)
            user_data.loc[user_data['id'] == user_id, ['username', 'color', 'team']] = [username, color, team]
            user_data.to_csv(self.user_db, index=False)
            
            drink_data = self.load_data_from_csv(self.drink_db)
            drink_data.loc[drink_data['id'] == user_id, ['username', 'team']] = [username, team]
            drink_data.to_csv(self.drink_db, index=False)
            
            return True
        except Exception as e:
            print(f"Error updating user: {e}")
            return False

    def update_team(self, old_team_name, new_team_name, color):
        try:
            team_data = self.load_data_from_csv(self.team_db)
            team_data.loc[team_data['team'] == old_team_name, ['team', 'color']] = [new_team_name, color]
            team_data.to_csv(self.team_db, index=False)
            
            user_data = self.load_data_from_csv(self.user_db)
            user_data.loc[user_data['team'] == old_team_name, 'team'] = new_team_name
            user_data.to_csv(self.user_db, index=False)
            
            drink_data = self.load_data_from_csv(self.drink_db)
            drink_data.loc[drink_data['team'] == old_team_name, 'team'] = new_team_name
            drink_data.to_csv(self.drink_db, index=False)
            
            return True
        except Exception as e:
            print(f"Error updating team: {e}")
            return False

    def add_drink(self, user_id, drink_type, timestamp=None):
        try:
            user_data = self.load_data_from_csv(self.user_db)
            user_info = user_data[user_data['id'] == user_id]
            
            if user_info.empty:
                return False
            
            username = user_info['username'].iloc[0]
            team = user_info['team'].iloc[0]
            
            if timestamp is None:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            count = 1 if drink_type == 'beer' else -1
            self.save_drink_to_csv(user_id, username, team, timestamp, vomit=(drink_type == 'vomit'))
            
            return True
        except Exception as e:
            print(f"Error adding drink: {e}")
            return False

    def delete_drink(self, user_id, timestamp):
        try:
            drink_data = self.load_data_from_csv(self.drink_db)
            drink_data = drink_data[~((drink_data['id'] == user_id) & (drink_data['timestamp'] == timestamp))]
            drink_data.to_csv(self.drink_db, index=False)
            return True
        except Exception as e:
            print(f"Error deleting drink: {e}")
            return False

    def update_drink_timestamp(self, user_id, old_timestamp, new_timestamp):
        try:
            drink_data = self.load_data_from_csv(self.drink_db)
            drink_data.loc[(drink_data['id'] == user_id) & (drink_data['timestamp'] == old_timestamp), 'timestamp'] = new_timestamp
            drink_data.to_csv(self.drink_db, index=False)
            return True
        except Exception as e:
            print(f"Error updating drink timestamp: {e}")
            return False

    def compress_image(self, image_path, output_path, quality=85, max_width=800, max_height=600):
        try:
            with Image.open(image_path) as img:
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                
                img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                
                img.save(output_path, 'JPEG', quality=quality, optimize=True)
                return True
        except Exception as e:
            print(f"Error compressing image: {e}")
            return False

    def create_thumbnail(self, image_path, thumbnail_path, size=(300, 200)):
        try:
            with Image.open(image_path) as img:
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                
                img.thumbnail(size, Image.Resampling.LANCZOS)
                
                img.save(thumbnail_path, 'JPEG', quality=85, optimize=True)
                return True
        except Exception as e:
            print(f"Error creating thumbnail: {e}")
            return False

    def get_all_photos(self):
        photos = []
        user_data = self.load_data_from_csv(self.user_db)
        
        print(f"📁 DEBUG: Looking for photos in: {self.pictures}")
        print(f"📁 DEBUG: Pictures directory exists: {os.path.exists(self.pictures)}")
        if os.path.exists(self.pictures):
            files = os.listdir(self.pictures)
            print(f"📁 DEBUG: Found {len(files)} files: {files}")
            for f in files:
                full_path = os.path.join(self.pictures, f)
                is_file = os.path.isfile(full_path)
                is_image = f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))
                print(f"📁 DEBUG: {f} -> file: {is_file}, image: {is_image}")
        else:
            print(f"❌ DEBUG: Pictures directory {self.pictures} does not exist")
        
        if not os.path.exists(self.pictures):
            print(f"DEBUG: Pictures directory {self.pictures} does not exist")
            return photos
        
        for filename in os.listdir(self.pictures):
            file_path = os.path.join(self.pictures, filename)
            if os.path.isfile(file_path) and filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                try:
                    parts = filename.split('_')
                    if len(parts) >= 3:
                        username = parts[0]
                        date_part = parts[1]
                        time_part = parts[2]
                        
                        file_stats = os.stat(file_path)
                        file_size = file_stats.st_size
                        created_time = datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                        
                        user_id = None
                        user_color = None
                        user_team = None
                        for _, user_row in user_data.iterrows():
                            if user_row['username'] == username:
                                user_id = user_row['id']
                                user_color = user_row.get('color')
                                user_team = user_row.get('team')
                                break
                        
                        thumbnail_filename = f"thumb_{filename}"
                        thumbnail_path = os.path.join(self.thumbnails, thumbnail_filename)
                        has_thumbnail = os.path.exists(thumbnail_path)
                        
                        photo_info = {
                            'filename': filename,
                            'username': username,
                            'user_id': user_id,
                            'user_color': user_color if user_color else '#000000',
                            'user_team': user_team if user_team else 'Unknown',
                            'timestamp': f"{date_part} {time_part.replace('-', ':')}",
                            'file_size': file_size,
                            'created_time': created_time,
                            'file_path': f"/pictures/{filename}",
                            'thumbnail_path': f"/thumbnails/{thumbnail_filename}" if has_thumbnail else f"/pictures/{filename}",
                            'has_thumbnail': has_thumbnail
                        }
                        photos.append(photo_info)
                    else:
                        file_stats = os.stat(file_path)
                        file_size = file_stats.st_size
                        created_time = datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                        
                        thumbnail_filename = f"thumb_{filename}"
                        thumbnail_path = os.path.join(self.thumbnails, thumbnail_filename)
                        has_thumbnail = os.path.exists(thumbnail_path)
                        
                        photo_info = {
                            'filename': filename,
                            'username': 'Unknown',
                            'user_id': None,
                            'user_color': '#000000',
                            'user_team': 'Unknown',
                            'timestamp': created_time,
                            'file_size': file_size,
                            'created_time': created_time,
                            'file_path': f"/pictures/{filename}",
                            'thumbnail_path': f"/thumbnails/{thumbnail_filename}" if has_thumbnail else f"/pictures/{filename}",
                            'has_thumbnail': has_thumbnail
                        }
                        photos.append(photo_info)
                        
                except Exception as e:
                    print(f"Error processing photo {filename}: {e}")
                    continue
        
        photos.sort(key=lambda x: x['created_time'], reverse=True)
        return photos

    def delete_photo(self, filename):
        try:
            file_path = os.path.join(self.pictures, filename)
            thumbnail_path = os.path.join(self.thumbnails, f"thumb_{filename}")
            
            success = False
            if os.path.exists(file_path):
                os.remove(file_path)
                success = True
                
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
                
            return success
        except Exception as e:
            print(f"Error deleting photo {filename}: {e}")
            return False

    def add_routes(self):

        @self.app.route("/admin/reset")
        @self.admin_required
        def admin_reset():
            return render_template('admin/reset.html')

        @self.app.route("/admin/reset", methods=["POST"])
        @self.admin_required
        def admin_reset_post():
            password = request.form.get('password')
            if password == self.admin_password:
                self.initialization()
                flash('All data has been successfully reset and archived!', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid admin password. Reset operation cancelled.', 'error')
                return redirect(url_for('admin_reset'))

        @self.app.route("/chart")
        def show_chart():
            app_running = self.is_app_running()
            return render_template('chart.html', app_running=app_running)

        @self.app.route("/")
        def show_increment():
            app_running = self.is_app_running()
            
            if app_running:
                user_id = request.cookies.get('user_id')
                if user_id and not self.validate_user_from_cookie(user_id):
                    flash('Your user account or team was not found. Please set up your profile again.', 'warning')
                    return redirect(url_for('show_setup'))
                elif not user_id:
                    return redirect(url_for('show_setup'))
            
            return render_template('increment.html', app_running=app_running)

        @self.app.route("/api/incrementVomit", methods=["POST"])
        def incrementVomit():
            if not self.is_app_running():
                return jsonify({'error': 'Application is currently stopped'}), 503
                
            user_id = request.form.get('user_id')
            user_data = self.load_data_from_csv(self.user_db)
            user_info = user_data[user_data['id'].str.lower() == user_id.lower()]
            if user_info.empty:
                return jsonify({'error': 'User not found!'}), 400

            username = str(user_info["username"].iloc[0])
            team = str(user_info["team"].iloc[0])

            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.save_drink_to_csv(user_id, username, team, current_time, vomit=True)

            return jsonify({'username': username, 'team':team}), 200

        @self.app.route("/api/incrementBeer", methods=["POST"])
        def incrementBeer():
                if not self.is_app_running():
                    return jsonify({'error': 'Application is currently stopped'}), 503
                    
                user_id = request.form.get('user_id')
                file = request.files.get('selfie')

                user_data = self.load_data_from_csv(self.user_db)
                user_info = user_data[user_data['id'].str.lower() == user_id.lower()]
                if user_info.empty:
                    return jsonify({'error': 'User not found!'}), 400

                username = str(user_info["username"].iloc[0])
                team = str(user_info["team"].iloc[0])

                drinks_data = self.load_data_from_csv(self.drink_db)
                user_drinks = drinks_data[drinks_data['id'].str.lower() == user_id.lower()]
                user_beers = user_drinks[user_drinks['count'] == 1]

                current_time = datetime.now()
                if not user_beers.empty:
                    last_20s_beers = user_beers[
                        user_beers['timestamp'].apply(
                            lambda x: (current_time - datetime.strptime(x, '%Y-%m-%d %H:%M:%S')).total_seconds() <= 20
                        )
                    ]
                    if len(last_20s_beers) >= 2:
                        return jsonify({
                            'error': 'Trop de bières ! Maximum 2 bières en 20 secondes',
                            'code': 429,
                            'cooldown': 20,
                            'elapsed': 0
                        }), 429

                    last_3min_beers = user_beers[
                        user_beers['timestamp'].apply(
                            lambda x: (current_time - datetime.strptime(x, '%Y-%m-%d %H:%M:%S')).total_seconds() <= 180
                        )
                    ]
                    if len(last_3min_beers) >= 5:
                        return jsonify({
                            'error': 'Trop de bières ! Maximum 5 bières en 3 minutes',
                            'code': 429,
                            'cooldown': 180,
                            'elapsed': 0
                        }), 429

                    last_20min_beers = user_beers[
                        user_beers['timestamp'].apply(
                            lambda x: (current_time - datetime.strptime(x, '%Y-%m-%d %H:%M:%S')).total_seconds() <= 1200
                        )
                    ]
                    if len(last_20min_beers) >= 10:
                        return jsonify({
                            'error': 'Trop de bières ! Maximum 10 bières en 20 minutes',
                            'code': 429,
                            'cooldown': 1200,
                            'elapsed': 0
                        }), 429

                    last_hour_beers = user_beers[
                        user_beers['timestamp'].apply(
                            lambda x: (current_time - datetime.strptime(x, '%Y-%m-%d %H:%M:%S')).total_seconds() <= 3600
                        )
                    ]
                    if len(last_hour_beers) >= 20:
                        return jsonify({
                            'error': 'Trop de bières ! Maximum 20 bières par heure',
                            'code': 429,
                            'cooldown': 3600,
                            'elapsed': 0
                        }), 429

                if file and self.allowed_file(file.filename):
                    filename = secure_filename(f"{username}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_{file.filename}")
                    file_path = os.path.join(self.app.config['UPLOAD_FOLDER'], filename)
                    
                    temp_path = file_path + '.temp'
                    file.save(temp_path)
                    
                    if self.compress_image(temp_path, file_path):
                        os.remove(temp_path)
                    else:
                        os.rename(temp_path, file_path)
                    
                    thumbnail_filename = f"thumb_{filename}"
                    thumbnail_path = os.path.join(self.thumbnails, thumbnail_filename)
                    self.create_thumbnail(file_path, thumbnail_path)

                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                self.save_drink_to_csv(user_id, username, team, current_time)

                return jsonify({'username': username, 'team':team}), 200
            

        @self.app.route("/setup")
        def show_setup():
            app_running = self.is_app_running()
            return render_template('setup.html', app_running=app_running)

        @self.app.route("/credits")
        def show_credits():
            return render_template('credits.html')

        @self.app.route("/api/set", methods=["POST"])
        def set_config():
            if not self.is_app_running():
                return jsonify({'error': 'Application is currently stopped'}), 503
                
            data = request.json
            username = data.get('username')
            team = data.get('team')
            color_name = data.get('nameColor')
            color_team = data.get('teamColor')

            if not username:
                return jsonify({'error': 'Username is required'}), 400
            if not team:
                return jsonify({'error': 'Team is required'}), 400

            if color_team:
                team_df = pd.read_csv(self.team_db)
                if not team_df.empty:
                    existing_team = team_df[(team_df['team'] == team)]
                    if not existing_team.empty:
                        return jsonify({'error': 'This team already exists'}), 400

                new_team = pd.DataFrame([[team, color_team]], columns=['team', 'color'])
                new_team.to_csv(self.team_db, mode='a', header=False, index=False)

            user_df = pd.read_csv(self.user_db)
            if not user_df.empty:
                existing_user = user_df[(user_df['username'] == username) & (user_df['team'] == team)]
                if not existing_user.empty:
                    user_id = str(existing_user["id"].iloc[0])
                    user_df.loc[(user_df['username'] == username) & (user_df['team'] == team), 'color'] = color_name
                    user_df.to_csv(self.user_db, index=False)

                    return jsonify({'code': 201, 'message': 'User color updated!', 'user_id': user_id}), 200

            user_id = str(uuid.uuid4())
            new_user = pd.DataFrame([[user_id, username, color_name, team]], columns=['id','username', 'color', 'team'])
            new_user.to_csv(self.user_db, mode='a', header=False, index=False)

            return jsonify({'code':200,'message': 'Setup saved successfully!', 'user_id':user_id}), 200

        @self.app.route("/api/data", methods=["GET"])
        def get_all_data():
            drinks = self.get_beers_data()
            return drinks.to_json(orient='records')

        @self.app.route("/api/top10", methods=["GET"])
        def get_top10():
            return jsonify(self.get_top_10_users())

        @self.app.route("/api/userlist", methods=["GET"])
        def get_user_list():
            return jsonify(self.get_user_list())

        @self.app.route("/api/teamlist", methods=["GET"])
        def get_team_list():
            return jsonify(self.get_team_list())

        @self.app.route("/api/teamdata", methods=["GET"])
        def get_team_data_route():
            return jsonify(self.get_team_data())
        
        @self.app.route("/api/userinfo/<user_id>", methods=["GET"])
        def get_user_info(user_id):
            return jsonify(self.get_user_info(user_id))

        @self.app.route("/api/app/status", methods=["GET"])
        def get_public_app_status():
            return jsonify({
                'running': self.is_app_running(),
                'status': 'running' if self.is_app_running() else 'stopped'
            }), 200

        @self.app.route("/admin")
        def admin_login():
            if 'admin_logged_in' in session and session['admin_logged_in']:
                return redirect(url_for('admin_dashboard'))
            return render_template('admin/login.html')

        @self.app.route("/admin/login", methods=["POST"])
        def admin_login_post():
            password = request.form.get('password')
            if password == self.admin_password:
                session['admin_logged_in'] = True
                flash('Successfully logged in as admin', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid admin password', 'error')
                return redirect(url_for('admin_login'))

        @self.app.route("/admin/logout")
        def admin_logout():
            session.pop('admin_logged_in', None)
            flash('Successfully logged out', 'info')
            return redirect(url_for('admin_login'))

        @self.app.route("/admin/dashboard")
        @self.admin_required
        def admin_dashboard():
            users = self.get_all_users()
            teams = self.get_all_teams()
            app_status = {
                'running': self.is_app_running(),
                'status_text': 'Running' if self.is_app_running() else 'Stopped'
            }
            return render_template('admin/dashboard.html', users=users, teams=teams, app_status=app_status)

        @self.app.route("/admin/users")
        @self.admin_required
        def admin_users():
            users = self.get_all_users()
            teams = self.get_team_list()
            return render_template('admin/users.html', users=users, teams=teams)

        @self.app.route("/admin/teams")
        @self.admin_required
        def admin_teams():
            teams = self.get_all_teams()
            return render_template('admin/teams.html', teams=teams)

        @self.app.route("/admin/drinks/<user_id>")
        @self.admin_required
        def admin_user_drinks(user_id):
            user_info = self.get_user_info(user_id)
            drinks = self.get_user_drinks(user_id)
            return render_template('admin/drinks.html', user_info=user_info[0] if user_info else None, drinks=drinks, user_id=user_id)

        @self.app.route("/admin/api/users", methods=["POST"])
        @self.admin_required
        def admin_create_user():
            data = request.json
            username = data.get('username')
            color = data.get('color', '#000000')
            team = data.get('team', 'No Team')
            
            if not username:
                return jsonify({'error': 'Username is required'}), 400
            
            user_id = str(uuid.uuid4())
            new_user = pd.DataFrame([[user_id, username, color, team]], columns=['id','username', 'color', 'team'])
            new_user.to_csv(self.user_db, mode='a', header=False, index=False)
            
            return jsonify({'message': 'User created successfully', 'user_id': user_id}), 201

        @self.app.route("/admin/api/users/<user_id>", methods=["PUT"])
        @self.admin_required
        def admin_update_user(user_id):
            data = request.json
            username = data.get('username')
            color = data.get('color')
            team = data.get('team')
            
            if not username:
                return jsonify({'error': 'Username is required'}), 400
            
            if self.update_user(user_id, username, color, team):
                return jsonify({'message': 'User updated successfully'}), 200
            else:
                return jsonify({'error': 'Failed to update user'}), 500

        @self.app.route("/admin/api/users/<user_id>", methods=["DELETE"])
        @self.admin_required
        def admin_delete_user(user_id):
            if self.delete_user(user_id):
                return jsonify({'message': 'User deleted successfully'}), 200
            else:
                return jsonify({'error': 'Failed to delete user'}), 500

        @self.app.route("/admin/api/teams", methods=["POST"])
        @self.admin_required
        def admin_create_team():
            data = request.json
            team_name = data.get('team')
            color = data.get('color', '#000000')
            
            if not team_name:
                return jsonify({'error': 'Team name is required'}), 400
            
            team_data = self.load_data_from_csv(self.team_db)
            if not team_data.empty and team_name in team_data['team'].values:
                return jsonify({'error': 'Team already exists'}), 400
            
            new_team = pd.DataFrame([[team_name, color]], columns=['team', 'color'])
            new_team.to_csv(self.team_db, mode='a', header=False, index=False)
            
            return jsonify({'message': 'Team created successfully'}), 201

        @self.app.route("/admin/api/teams/<team_name>", methods=["PUT"])
        @self.admin_required
        def admin_update_team(team_name):
            data = request.json
            new_team_name = data.get('team')
            color = data.get('color')
            
            if not new_team_name:
                return jsonify({'error': 'Team name is required'}), 400
            
            if self.update_team(team_name, new_team_name, color):
                return jsonify({'message': 'Team updated successfully'}), 200
            else:
                return jsonify({'error': 'Failed to update team'}), 500

        @self.app.route("/admin/api/teams/<team_name>", methods=["DELETE"])
        @self.admin_required
        def admin_delete_team(team_name):
            if self.delete_team(team_name):
                return jsonify({'message': 'Team deleted successfully'}), 200
            else:
                return jsonify({'error': 'Failed to delete team'}), 500

        @self.app.route("/admin/api/drinks", methods=["POST"])
        @self.admin_required
        def admin_add_drink():
            data = request.json
            user_id = data.get('user_id')
            drink_type = data.get('type', 'beer')  # 'beer' or 'vomit'
            timestamp = data.get('timestamp')
            
            if not user_id:
                return jsonify({'error': 'User ID is required'}), 400
            
            if self.add_drink(user_id, drink_type, timestamp):
                return jsonify({'message': 'Drink added successfully'}), 201
            else:
                return jsonify({'error': 'Failed to add drink'}), 500

        @self.app.route("/admin/api/drinks/<user_id>/<timestamp>", methods=["DELETE"])
        @self.admin_required
        def admin_delete_drink(user_id, timestamp):
            if self.delete_drink(user_id, timestamp):
                return jsonify({'message': 'Drink deleted successfully'}), 200
            else:
                return jsonify({'error': 'Failed to delete drink'}), 500

        @self.app.route("/admin/api/drinks/<user_id>/<old_timestamp>", methods=["PUT"])
        @self.admin_required
        def admin_update_drink(user_id, old_timestamp):
            data = request.json
            new_timestamp = data.get('timestamp')
            
            if not new_timestamp:
                return jsonify({'error': 'New timestamp is required'}), 400
            
            if self.update_drink_timestamp(user_id, old_timestamp, new_timestamp):
                return jsonify({'message': 'Drink timestamp updated successfully'}), 200
            else:
                return jsonify({'error': 'Failed to update drink timestamp'}), 500

        @self.app.route("/pictures/<filename>")
        @self.admin_required
        def serve_photo(filename):
            if not os.path.exists(os.path.join(self.pictures, filename)):
                return "Photo not found", 404
            return send_from_directory(self.pictures, filename)

        @self.app.route("/thumbnails/<filename>")
        @self.admin_required
        def serve_thumbnail(filename):
            if not os.path.exists(os.path.join(self.thumbnails, filename)):
                return "Thumbnail not found", 404
            return send_from_directory(self.thumbnails, filename)

        @self.app.route("/admin/photos")
        @self.admin_required
        def admin_photos():
            print("=" * 50)
            print("🔍 ROUTE DEBUG: /admin/photos called!")
            print("=" * 50)
            try:
                photos = self.get_all_photos()
                print(f"🔍 DEBUG: get_all_photos returned {len(photos)} photos")
                for i, photo in enumerate(photos):
                    print(f"🔍 DEBUG: Photo {i}: {photo.get('filename', 'Unknown')}")
                print("🔍 DEBUG: Rendering template with photos")
                return render_template('admin/photos.html', photos=photos)
            except Exception as e:
                print(f"❌ ERROR in admin_photos: {e}")
                import traceback
                traceback.print_exc()
                return f"Error: {e}", 500

        @self.app.route("/admin/api/photos/<filename>", methods=["DELETE"])
        @self.admin_required
        def delete_photo_api(filename):
            if self.delete_photo(filename):
                return jsonify({'message': 'Photo deleted successfully'}), 200
            else:
                return jsonify({'error': 'Failed to delete photo'}), 500

        @self.app.route("/admin/api/app/start", methods=["POST"])
        @self.admin_required
        def start_app_api():
            if self.start_application():
                flash('Application started successfully', 'success')
                return jsonify({'message': 'Application started successfully', 'status': 'running'}), 200
            else:
                return jsonify({'error': 'Failed to start application'}), 500

        @self.app.route("/admin/api/app/stop", methods=["POST"])
        @self.admin_required
        def stop_app_api():
            if self.stop_application():
                flash('Application stopped successfully', 'info')
                return jsonify({'message': 'Application stopped successfully', 'status': 'stopped'}), 200
            else:
                return jsonify({'error': 'Failed to stop application'}), 500

        @self.app.route("/admin/api/app/restart", methods=["POST"])
        @self.admin_required
        def restart_app_api():
            if self.restart_application():
                flash('Application restarted successfully', 'success')
                return jsonify({'message': 'Application restarted successfully', 'status': 'running'}), 200
            else:
                return jsonify({'error': 'Failed to restart application'}), 500

        @self.app.route("/admin/api/app/status", methods=["GET"])
        @self.admin_required
        def get_app_status_api():
            return jsonify({
                'running': self.is_app_running(),
                'status': 'running' if self.is_app_running() else 'stopped'
            }), 200


    def run(self, host='127.0.0.1', port=5000, debug=True, ssl_context=None):
        self.app.run(host=host, port=port, debug=debug, ssl_context=ssl_context)


if __name__ == "__main__":
    import os
    
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 80))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'
    
    print(f"Beer Counter App - Starting on {host}:{port}")

    if '--reset' in sys.argv:
        app = DrinkApp(reset=True)
    else:
        app = DrinkApp(reset=False)
    app.run(host=host, port=port, debug=debug)
