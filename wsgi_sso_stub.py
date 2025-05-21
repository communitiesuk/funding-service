from gevent import monkey

from stubs.sso import create_sso_stub_app

monkey.patch_all()

app = create_sso_stub_app()

if __name__ == "__main__":
    app.run()
