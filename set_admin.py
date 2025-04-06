from app import app, db, User

# Start application context explicitly
with app.app_context():
    username = input("Enter the username to promote to admin: ")

    # Query the user by username
    user = User.query.filter_by(username=username).first()

    if user:
        user.role = 'admin'
        db.session.commit()
        print(f"✅ User '{username}' has been promoted to admin.")
    else:
        print(f"❌ User '{username}' not found.")
