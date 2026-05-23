from app import create_app, db
import os

app = create_app()

os.makedirs(app.instance_path, exist_ok=True)

with app.app_context():
    db_path = os.path.join(app.instance_path, "storage.db")

    if not os.path.exists(db_path):
        print("Membuat storage.db baru...")
    db.create_all()

print(app.url_map)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

