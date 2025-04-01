from app import app

# This is the entry point for the application
# The actual app is initialized in app.py

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)