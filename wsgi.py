from app import create_app

app = create_app()

if __name__ == "__main__":
    # 5000 は macOS の AirPlay レシーバーが占有していて 403 になる
    app.run(debug=True, port=5001)
