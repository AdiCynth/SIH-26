import subprocess

from flask import Flask, request

app = Flask(__name__)


@app.route("/calc")
def calc():
    return str(eval(request.args["expr"]))


@app.route("/ping")
def ping():
    host = request.args["host"]
    return subprocess.check_output(f"ping -c 1 {host}", shell=True)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
