from flask import Flask, request
from google.appengine.api import wrap_wsgi_app

from lljbot import LljPage, SendPage, MessagePage, PromoPage, VerifyPage
from secrets import TOKEN

app = Flask(__name__)
app.wsgi_app = wrap_wsgi_app(app.wsgi_app)

lljPage = LljPage()
sendPage = SendPage()
messagePage = MessagePage()
promoPage = PromoPage()
verifyPage = VerifyPage()

@app.route('/', methods=['GET'])
def hello():
    return 'LLJBot backend running...\n'

@app.route('/' + TOKEN, methods=['POST'])
def replyMessage():
    return lljPage.post(request.json)

@app.route('/send', methods=['GET', 'POST'])
def send():
    if request.method == 'GET':
        return sendPage.get()
    else:
        return sendPage.post()

@app.route('/message', methods=['POST'])
def message():
    return messagePage.post(request.data)

@app.route('/promo', methods=['GET', 'POST'])
def promo():
    if request.method == 'GET':
        return promoPage.get()
    else:
        return promoPage.post()

@app.route('/verify', methods=['GET', 'POST'])
def verify():
    if request.method == 'GET':
        return verifyPage.get()
    else:
        return verifyPage.post(request.data)
