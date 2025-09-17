import os
import sys
import shutil
import pandas as pd
from datetime import datetime
from flask import Flask, jsonify, request, render_template
from werkzeug.utils import secure_filename
import uuid
class DrinkApp:
    def __init__(self, reset):
        self.app = Flask(__name__)

        self.archives = "./archives"
        self.database = "./database"
        self.drink_db = os.path.join(self.database, "drink_db.csv")
        self.user_db = os.path.join(self.database, "user_db.csv")
        self.team_db = os.path.join(self.database, "team_db.csv")
        self.total_drinks = "total_drinks.csv"
        self.pictures = "./pictures"
        self.app.config['UPLOAD_FOLDER'] = self.pictures
        self.allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
        self.admin_password = "test741"

        os.makedirs(self.database, exist_ok=True)
        os.makedirs(self.pictures, exist_ok=True)
        os.makedirs(self.archives, exist_ok=True)
        if reset or not os.path.exists(self.drink_db) or not os.path.exists(self.user_db) or not os.path.exists(self.team_db):
            self.initialization()

        self.add_routes()

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
            return [].to_dict()

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



    def add_routes(self):

        @self.app.route("/reset", methods=["GET", "POST"])
        def reset_data():
            if request.method == "POST":
                password = request.form.get('password')
                if password == self.admin_password:
                    self.initialization()
                    return jsonify({'message': 'Data reset successful!'}), 200
                else:
                    return jsonify({'error': 'Invalid password'}), 401
            return render_template('reset.html')

        @self.app.route("/chart")
        def show_chart():
            return render_template('chart.html')

        @self.app.route("/")
        def show_increment():
            return render_template('increment.html')

        @self.app.route("/api/incrementVomit", methods=["POST"])
        def incrementVomit():
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
                    file.save(os.path.join(self.app.config['UPLOAD_FOLDER'], filename))

                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                self.save_drink_to_csv(user_id, username, team, current_time)

                return jsonify({'username': username, 'team':team}), 200
            

        @self.app.route("/setup")
        def show_setup():
            return render_template('setup.html')

        @self.app.route("/credits")
        def show_credits():
            return render_template('credits.html')

        @self.app.route("/api/set", methods=["POST"])
        def set_config():
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

        #@self.app.route("/", methods=["GET"])
        #@self.app.before_request
        #def restrict_admin_routes():
         #   admin_routes = ["/reset", "/chart"]
            
          #  if request.path in admin_routes:
                #host = request.headers.get('Host', '')
                # Vérifier si la requête provient du sous-sous-domaine admin.boissons.example.com
                #if not host.startswith('carapils'):
                #return jsonify({'error': 'Acces denied'}), 403
            

           # user_routes = ["/setup", "/api", "/"]
           # if request.path in user_routes:
            #    host = request.headers.get('Host', '')
                
                #if not host.startswith('carapils'):
                #return jsonify({'erreur': 'Acces denied'}), 403


    def run(self, host='127.0.0.1', port=5000, debug=True, ssl_context=None):
        self.app.run(host=host, port=port, debug=debug, ssl_context=ssl_context)


if __name__ == "__main__":
    import os
    
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 80))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'
    
    print("Beer Counter starting...")
    print(f"Available on {host}:{port}")
    print(f"Debug: {debug}")

    if '--reset' in sys.argv:
        app = DrinkApp(reset=True)
    else:
        app = DrinkApp(reset=False)
    app.run(host=host, port=port, debug=debug)
