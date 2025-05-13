from gevent import monkey

monkey.patch_all()

from app import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    app.run()
