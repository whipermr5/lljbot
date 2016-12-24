import webapp2
import logging
import json
import HTMLParser
import textwrap
import scriptures
from google.appengine.api import urlfetch, taskqueue
from google.appengine.ext import db
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

def get_devo(delta=0):
    def strip_markdown(string):
        return string.replace('*', ' ').replace('_', ' ')

    today_date = datetime.utcnow() + timedelta(hours=8, days=delta)
    date_url = today_date.strftime('%Y-%m-%d')
    devo_url = 'http://qt.swim.org/user_dir/living/user_print_web.php?edit_all=' + date_url

    try:
        result = urlfetch.fetch(devo_url, deadline=10)
    except Exception as e:
        logging.warning('Error fetching devo:\n' + str(e))
        return None

    try:
        html = result.content
        soup = BeautifulSoup(html, 'lxml')

        date = today_date.strftime('%b %-d, %Y ({})').format(today_date.strftime('%a').upper())
        heading = strip_markdown(soup.select_one('.main_title').text).strip()
        verse = strip_markdown(soup.select_one('.bible_no').text).lstrip('[ ').rstrip(' ]')
        verse = scriptures.reference_to_string(*scriptures.extract(verse)[0])
        first_word = verse.partition(' ')[0]
        if first_word in ('I', 'II', 'III'):
            verse = str(len(first_word)) + verse.lstrip('I')
        elif first_word == 'Revelation':
            verse = first_word + verse[26:]

        lines = soup.select_one('.main_body').text.splitlines()
        passage = ''
        for line in lines:
            idx = line.find(' ')
            num = '_' + strip_markdown(line[:idx]).rstrip('.') + '_'
            rest_of_line = strip_markdown(line[idx:]).strip()
            passage += '{} {}\n'.format(num, rest_of_line)
        passage = passage.strip()

        ref_soup = soup.select_one('.main_body2')
        for tag in ref_soup.select('b'):
            text = strip_markdown(tag.text).strip()
            tag.string = '*' + text.replace(' ', '\a') + '*'
        reflection = ref_soup.text.strip() + '\n\n'
        reflection += strip_markdown(soup.select_one('.main_body3').text).strip()

        prayer = strip_markdown(soup.select('.main_body2')[1].text).strip()

        daynames = ['Yesterday\'s', 'Today\'s', 'Tomorrow\'s']

        devo = u'\U0001F4C5' + ' ' + daynames[delta + 1] + ' QT - _' + date + '_\n\n' + \
               '*' + heading + '*\n' + verse + '\n\n' + \
               u'\U0001F4D9' + ' *Scripture* _(NIV)_\n\n' + passage + '\n\n' + \
               u'\U0001F4DD' + ' *Reflection*\n\n' + reflection + '\n\n' + \
               u'\U0001F64F' + ' *Prayer*\n\n' + prayer
        return devo

    except:
        if delta == -1:
            return 'Sorry, the LLJ website is no longer hosting yesterday\'s material.'
        elif delta == 0:
            return 'Sorry, the LLJ website does not have today\'s material yet.'
        else:
            return 'Sorry, the LLJ website hasn\'t made tomorrow\'s material available yet.'

def get_devo_old(delta=0):
    date = (datetime.utcnow() + timedelta(hours=8, days=delta)).strftime('%Y-%m-%d')
    devo_url = 'http://www.duranno.com/livinglife/qt/reload_default.asp?OD=' + date

    try:
        result = urlfetch.fetch(devo_url, deadline=10)
    except Exception as e:
        logging.warning('Error fetching devo:\n' + str(e))
        return None

    content = result.content.decode('cp949', 'ignore')

    h = HTMLParser.HTMLParser()

    def prep_str(string):
        string = string.replace('<br>', '\n')
        return h.unescape(string).strip()

    def prep_passage(string):
        result = ''
        first = string.find('<!-- bible verse and text -->')
        string = string[first:]
        while '<!-- bible verse and text -->' in string:
            start = string.find('<div class="listTxt">') + 21
            end = string.find('</div>', start)
            num = '_' + prep_str(string[start:end]) + '_'
            start = string.find('<div class="listCon">') + 21
            end = string.find('</div>', start)
            text = prep_str(string[start:end])
            result += num + ' ' + strip_markdown(text) + '\n'
            string = string[end:]
        return result.strip()

    def strip_markdown(string):
        return string.replace('*', ' ').replace('_', ' ')

    def get_remote_date(content):
        start = content.find('var videoNowDate = "') + 20
        return content[start:start + 10]

    if delta != 0 and get_remote_date(content) != date:
        if delta == -1:
            return 'Sorry, the LLJ website is no longer hosting yesterday\'s material.'
        else:
            return 'Sorry, the LLJ website hasn\'t made tomorrow\'s material available yet.'

    title_start = content.find('<!-- today QT -->')
    title_end = content.find('<!-- bible words -->')
    title = prep_str(content[title_start:title_end])
    start = title.find('<div class="today_m">') + 21
    end = title.find('</div>', start)
    date = strip_markdown(prep_str(title[start:end]))
    start = title.find('<div class="title">') + 59
    end = title.find('</a>', start)
    heading = strip_markdown(prep_str(title[start:end]))
    start = title.find('<div class="sub_title">') + 23
    end = title.find('</div>', start)
    verse = strip_markdown(prep_str(title[start:end]))

    passage_start = title_end
    passage_end = content.find('<!-- Reflection-->')
    passage = prep_passage(content[passage_start:passage_end])

    reflection_start = passage_end
    reflection_end = content.find('<!--  Letter to God -->')
    reflection = content[reflection_start:reflection_end]
    start = reflection.find('<div class="con">') + 17
    end = reflection.find('</div>', start)
    reflection = strip_markdown(prep_str(reflection[start:end]))

    prayer_start = reflection_end
    prayer_end = content.find('<!-- Share SNS -->')
    prayer = content[prayer_start:prayer_end]
    start = prayer.find('<div class="con" style="padding-top:25px;">') + 43
    end = prayer.find('</div>', start)
    prayer = strip_markdown(prep_str(prayer[start:end]))

    daynames = ['Yesterday\'s', 'Today\'s', 'Tomorrow\'s']

    devo = u'\U0001F4C5' + ' ' + daynames[delta + 1] + ' QT - _' + date + '_\n\n' + \
           '*' + heading + '*\n' + verse + '\n\n' + \
           u'\U0001F4D9' + ' *Scripture* _(NIV)_\n\n' + passage + '\n\n' + \
           u'\U0001F4DD' + ' *Reflection*\n\n' + reflection + '\n\n' + \
           u'\U0001F64F' + ' *Prayer*\n\n' + prayer
    return devo

from secrets import TOKEN, ADMIN_ID, BOT_ID, BOTFAMILY_HASH
TELEGRAM_URL = 'https://api.telegram.org/bot' + TOKEN
TELEGRAM_URL_SEND = TELEGRAM_URL + '/sendMessage'
TELEGRAM_URL_SEND_PHOTO = TELEGRAM_URL + '/sendPhoto'
TELEGRAM_URL_CHAT_ACTION = TELEGRAM_URL + '/sendChatAction'
JSON_HEADER = {'Content-Type': 'application/json;charset=utf-8'}

LOG_SENT = '{} {} sent to uid {} ({})'
LOG_ENQUEUED = 'Enqueued {} to uid {} ({})'
LOG_DID_NOT_SEND = 'Did not send {} to uid {} ({}): {}'
LOG_ERROR_SENDING = 'Error sending {} to uid {} ({}):\n{}'
LOG_ERROR_DAILY = 'Error enqueueing dailies:\n'
LOG_ERROR_QUERY = 'Error querying uid {} ({}): {}'
LOG_TYPE_FEEDBACK = 'Type: Feedback\n'
LOG_TYPE_START_NEW = 'Type: Start (new user)'
LOG_TYPE_START_EXISTING = 'Type: Start (existing user)'
LOG_TYPE_NON_TEXT = 'Type: Non-text'
LOG_TYPE_NON_MESSAGE = 'Type: Non-message'
LOG_TYPE_COMMAND = 'Type: Command\n'
LOG_UNRECOGNISED = 'Unrecognised command'
LOG_USER_MIGRATED = 'User {} migrated to uid {} ({})'
LOG_USER_DELETED = 'Deleted uid {} ({})'
LOG_USER_REACHABLE = 'Uid {} ({}) is still reachable'
LOG_USER_UNREACHABLE = 'Unable to reach uid {} ({}): {}'

RECOGNISED_ERROR_PARSE = 'Bad Request: Can\'t parse message text'
RECOGNISED_ERROR_MIGRATE = 'Bad Request: group chat is migrated to a supergroup chat'
RECOGNISED_ERRORS = ('PEER_ID_INVALID',
                     'Bot was blocked by the user',
                     'Forbidden: user is deleted',
                     'Forbidden: user is deactivated',
                     'Forbidden: User is deactivated',
                     'Forbidden: Bot was blocked by the user',
                     'Forbidden: bot was kicked from the group chat',
                     'Forbidden: bot was kicked from the channel chat',
                     'Forbidden: bot was kicked from the supergroup chat',
                     'Forbidden: bot is not a member of the supergroup chat',
                     'Forbidden: Bot can\'t initiate conversation with a user',
                     'Bad Request: chat not found',
                     'Bad Request: PEER_ID_INVALID',
                     'Bad Request: group chat was deactivated',
                     RECOGNISED_ERROR_MIGRATE)

def telegram_post(data, deadline=3):
    return urlfetch.fetch(url=TELEGRAM_URL_SEND, payload=data, method=urlfetch.POST,
                          headers=JSON_HEADER, deadline=deadline)

def telegram_query(uid, deadline=3):
    data = json.dumps({'chat_id': uid, 'action': 'typing'})
    return urlfetch.fetch(url=TELEGRAM_URL_CHAT_ACTION, payload=data, method=urlfetch.POST,
                          headers=JSON_HEADER, deadline=deadline)

def telegram_photo(data, deadline=3):
    return urlfetch.fetch(url=TELEGRAM_URL_SEND_PHOTO, payload=data, method=urlfetch.POST,
                          headers=JSON_HEADER, deadline=deadline)

def get_today_time():
    today = (datetime.utcnow() + timedelta(hours=8)).date()
    today_time = datetime(today.year, today.month, today.day) - timedelta(hours=8)
    return today_time

class User(db.Model):
    username = db.StringProperty(indexed=False)
    first_name = db.StringProperty(multiline=True, indexed=False)
    last_name = db.StringProperty(multiline=True, indexed=False)
    created = db.DateTimeProperty(auto_now_add=True)
    last_received = db.DateTimeProperty(auto_now_add=True, indexed=False)
    last_sent = db.DateTimeProperty(indexed=False)
    last_auto = db.DateTimeProperty(auto_now_add=True)
    active = db.BooleanProperty(default=True)
    promo = db.BooleanProperty(default=False)

    def get_uid(self):
        return self.key().name()

    def get_name_string(self):
        def prep(string):
            return string.encode('utf-8', 'ignore').strip()

        name = prep(self.first_name)
        if self.last_name:
            name += ' ' + prep(self.last_name)
        if self.username:
            name += ' @' + prep(self.username)

        return name

    def get_description(self):
        user_type = 'group' if self.is_group() else 'user'
        return user_type + ' ' + self.get_name_string()

    def is_group(self):
        return int(self.get_uid()) < 0

    def is_active(self):
        return self.active

    def set_active(self, active):
        self.active = active
        self.put()

    def set_promo(self, promo):
        self.promo = promo
        self.put()

    def update_last_received(self):
        self.last_received = datetime.now()
        self.put()

    def update_last_sent(self):
        self.last_sent = datetime.now()
        self.put()

    def update_last_auto(self):
        self.last_auto = get_today_time()
        self.put()

    def migrate_to(self, uid):
        props = dict((prop, getattr(self, prop)) for prop in self.properties().keys())
        props.update(key_name=str(uid))
        new_user = User(**props)
        new_user.put()
        self.delete()
        return new_user

def get_user(uid):
    key = db.Key.from_path('User', str(uid))
    user = db.get(key)
    if user == None:
        user = User(key_name=str(uid), first_name='-')
        user.put()
    return user

def update_profile(uid, uname, fname, lname):
    existing_user = get_user(uid)
    if existing_user:
        existing_user.username = uname
        existing_user.first_name = fname
        existing_user.last_name = lname
        existing_user.update_last_received()
        #existing_user.put()
        return existing_user
    else:
        user = User(key_name=str(uid), username=uname, first_name=fname, last_name=lname)
        user.put()
        return user

def send_message(user_or_uid, text, msg_type='message', force_reply=False, markdown=False,
                 disable_web_page_preview=False):
    try:
        uid = str(user_or_uid.get_uid())
        user = user_or_uid
    except AttributeError:
        uid = str(user_or_uid)
        user = get_user(user_or_uid)

    def send_short_message(text, countdown=0):
        build = {
            'chat_id': uid,
            'text': text.replace('\a', ' ')
        }

        if force_reply:
            build['reply_markup'] = {'force_reply': True}
        if markdown:
            build['parse_mode'] = 'Markdown'
        if msg_type == 'promo' or disable_web_page_preview:
            build['disable_web_page_preview'] = True

        data = json.dumps(build)

        def queue_message():
            payload = json.dumps({
                'msg_type': msg_type,
                'data': data
            })
            taskqueue.add(url='/message', payload=payload, countdown=countdown)
            logging.info(LOG_ENQUEUED.format(msg_type, uid, user.get_description()))

        if msg_type in ('daily', 'promo', 'mass'):
            if msg_type == 'daily':
                user.update_last_auto()
            elif msg_type == 'promo':
                user.set_promo(True)

            queue_message()
            return

        try:
            result = telegram_post(data)
        except Exception as e:
            logging.warning(LOG_ERROR_SENDING.format(msg_type, uid, user.get_description(), str(e)))
            queue_message()
            return

        response = json.loads(result.content)
        error_description = str(response.get('description'))

        if error_description.startswith(RECOGNISED_ERROR_PARSE):
            if build.get('parse_mode'):
                del build['parse_mode']
            data = json.dumps(build)
            queue_message()

        elif handle_response(response, user, uid, msg_type) == False:
            queue_message()

    if len(text) > 4096:
        chunks = textwrap.wrap(text, width=4096, replace_whitespace=False, drop_whitespace=False)
        i = 0
        for chunk in chunks:
            send_short_message(chunk, i)
            i += 1
    else:
        send_short_message(text)

def handle_response(response, user, uid, msg_type):
    if response.get('ok') == True:
        msg_id = str(response.get('result').get('message_id'))
        logging.info(LOG_SENT.format(msg_type.capitalize(), msg_id, uid, user.get_description()))
        user.update_last_sent()

    else:
        error_description = str(response.get('description'))
        if error_description.startswith(RECOGNISED_ERROR_PARSE):
            logging.warning(LOG_ERROR_SENDING.format(msg_type, uid, user.get_description(),
                                                     error_description))
            return True

        if error_description not in RECOGNISED_ERRORS:
            logging.warning(LOG_ERROR_SENDING.format(msg_type, uid, user.get_description(),
                                                     error_description))
            return False

        logging.info(LOG_DID_NOT_SEND.format(msg_type, uid, user.get_description(),
                                             error_description))
        if error_description == RECOGNISED_ERROR_MIGRATE:
            new_uid = response.get('parameters', {}).get('migrate_to_chat_id')
            if new_uid:
                user = user.migrate_to(new_uid)
                logging.info(LOG_USER_MIGRATED.format(uid, new_uid, user.get_description()))
        else:
            user_description = user.get_description()
            user.delete()
            logging.info(LOG_USER_DELETED.format(uid, user_description))
            return True

        user.set_active(False)
        if msg_type == 'promo':
            user.set_promo(False)

    return True

def send_typing(uid):
    data = json.dumps({'chat_id': uid, 'action': 'typing'})
    try:
        rpc = urlfetch.create_rpc()
        urlfetch.make_fetch_call(rpc, url=TELEGRAM_URL_CHAT_ACTION, payload=data,
                                 method=urlfetch.POST, headers=JSON_HEADER)
    except:
        return

class MainPage(webapp2.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write('LLJBot backend running...\n')

class LljPage(webapp2.RequestHandler):
    CMD_LIST = '\n\n' + \
               '/today - get today\'s material\n' + \
               '/yesterday - get yesterday\'s material\n' + \
               '/tomorrow - get tomorrow\'s material'
    CMD_UNSUB = '/unsubscribe - disable automatic updates'
    CMD_SUB = '/subscribe - re-enable automatic updates'
    CMD_LIST_UNSUB = CMD_LIST + '\n' + CMD_UNSUB
    CMD_LIST_SUB = CMD_LIST + '\n' + CMD_SUB

    WELCOME_GROUP = 'Hello, friends in {}! Thanks for adding me in! ' + \
                    'This group chat is now subscribed.'
    WELCOME_USER = 'Hello, {}! Welcome! You are now subscribed.'
    WELCOME_GET_STARTED = ' You may enter one of the following commands:' + CMD_LIST_UNSUB + \
                          '\n\nIn the meantime, here\'s today\'s material to get you started!'

    REMOTE_ERROR = 'Sorry, I\'m having some difficulty accessing the LLJ website. ' + \
                   'Please try again later.'

    SUB_ALREADY = 'Looks like you are already subscribed!'
    SUB_SUCCESS = 'Success!'
    SUB_APPENDIX = ' You will receive material every day at midnight, Singapore time :)'

    UNSUB_ALREADY = 'Looks like you already unsubscribed! Don\'t worry; ' + \
                    'you won\'t be receiving any more automatic updates.'
    UNSUB_SUCCESS = 'You have successfully unsubscribed and will no longer receive ' + \
                    'automatic updates. Use /subscribe if this was a mistake.'
    UNSUB_APPENDIX = ' You can still get material manually by using the commands :)'

    SETTINGS_SUB = 'You are currently *subscribed*. Use /unsubscribe to change this.'
    SETTINGS_UNSUB = 'You are currently *not subscribed*. Use /subscribe if this is a mistake.'

    HELP = 'Hi {}, please enter one of the following commands:'
    HELP_LINK = 'Enjoy using LLJ Bot? Click the link below to rate it!\n' + \
                'https://telegram.me/storebot?start=lljbot'

    FEEDBACK_STRING = 'Please reply with your feedback. ' + \
                      'I will relay the message to my developer.'
    FEEDBACK_ALERT = 'Feedback from {} ({}){}:\n{}'
    FEEDBACK_SUCCESS = 'Your message has been sent to my developer. ' + \
                       'Thanks for your feedback, {}!'

    UNRECOGNISED = 'Sorry {}, I couldn\'t understand that. ' + \
                   'Please enter one of the following commands:'

    def post(self):
        data = json.loads(self.request.body)
        logging.debug(self.request.body)

        msg = data.get('message')
        if not msg:
            logging.info(LOG_TYPE_NON_MESSAGE)
            return

        msg_chat = msg.get('chat')
        msg_from = msg.get('from')

        if msg_chat.get('type') == 'private':
            uid = msg_from.get('id')
            first_name = msg_from.get('first_name')
            last_name = msg_from.get('last_name')
            username = msg_from.get('username')
        else:
            uid = msg_chat.get('id')
            first_name = msg_chat.get('title')
            last_name = None
            username = None

        user = update_profile(uid, username, first_name, last_name)

        actual_id = msg_from.get('id')
        name = first_name.encode('utf-8', 'ignore').strip()
        actual_username = msg_from.get('username')
        if actual_username:
            actual_username = actual_username.encode('utf-8', 'ignore').strip()
        actual_name = msg_from.get('first_name').encode('utf-8', 'ignore').strip()
        actual_last_name = msg_from.get('last_name')
        if actual_last_name:
            actual_last_name = actual_last_name.encode('utf-8', 'ignore').strip()
        text = msg.get('text')
        if text:
            text = text.encode('utf-8', 'ignore')

        if text == '/botfamily_verification_code':
            send_message(user, BOTFAMILY_HASH)
            send_message(ADMIN_ID, 'Botfamily verified! :D')
            return

        def get_from_string():
            name_string = actual_name
            if actual_last_name:
                name_string += ' ' + actual_last_name
            if actual_username:
                name_string += ' @' + actual_username
            return name_string

        msg_reply = msg.get('reply_to_message')
        if msg_reply and str(msg_reply.get('from').get('id')) == BOT_ID and \
                         msg_reply.get('text') == self.FEEDBACK_STRING:
            logging.info(LOG_TYPE_FEEDBACK + str(text))

            if user.is_group():
                group_string = ' via group {} ({})'.format(name, uid)
            else:
                group_string = ''

            msg_dev = self.FEEDBACK_ALERT.format(get_from_string(), actual_id, group_string, text)
            msg_user = self.FEEDBACK_SUCCESS.format(actual_name)

            send_message(ADMIN_ID, msg_dev)
            send_message(user, msg_user)
            return

        if user.last_sent == None or text == '/start':
            if user.last_sent == None:
                logging.info(LOG_TYPE_START_NEW)
                new_user = True
            else:
                logging.info(LOG_TYPE_START_EXISTING)
                new_user = False

            if not user.is_active():
                user.set_active(True)

            if user.is_group():
                response = self.WELCOME_GROUP.format(name)
            else:
                response = self.WELCOME_USER.format(name)
            response += self.WELCOME_GET_STARTED
            send_message(user, response)

            send_typing(uid)
            response = get_devo()
            if response == None:
                response = self.REMOTE_ERROR
            send_message(user, response, markdown=True)

            if new_user:
                if user.is_group():
                    new_alert = 'New group: "{}" via user: {}'.format(name, get_from_string())
                else:
                    new_alert = 'New user: ' + get_from_string()
                send_message(ADMIN_ID, new_alert)

            return

        if text == None:
            logging.info(LOG_TYPE_NON_TEXT)
            migrate_to_chat_id = msg.get('migrate_to_chat_id')
            if migrate_to_chat_id:
                new_uid = migrate_to_chat_id
                user = user.migrate_to(new_uid)
                logging.info(LOG_USER_MIGRATED.format(uid, new_uid, user.get_description()))
            return

        logging.info(LOG_TYPE_COMMAND + text)

        cmd = text.lower().strip()
        short_cmd = ''.join(cmd.split())

        def is_command(word):
            flexi_pattern = ('/{}@lljbot'.format(word), '@lljbot/{}'.format(word))
            return cmd == '/' + word or short_cmd.startswith(flexi_pattern)

        if is_command('today'):
            send_typing(uid)
            response = get_devo()
            if response == None:
                response = self.REMOTE_ERROR
            elif response.startswith('Sorry'):
                response = get_devo_old()
                if response == None:
                    response = self.REMOTE_ERROR

            send_message(user, response, markdown=True)

        elif is_command('yesterday'):
            send_typing(uid)
            response = get_devo(-1)
            if response == None:
                response = self.REMOTE_ERROR
            elif response.startswith('Sorry'):
                response = get_devo_old(-1)
                if response == None:
                    response = self.REMOTE_ERROR

            send_message(user, response, markdown=True)

        elif is_command('tomorrow'):
            send_typing(uid)
            response = get_devo(1)
            if response == None:
                response = self.REMOTE_ERROR
            elif response.startswith('Sorry'):
                response = get_devo_old(1)
                if response == None:
                    response = self.REMOTE_ERROR

            send_message(user, response, markdown=True)

        elif is_command('subscribe'):
            if user.is_active():
                response = self.SUB_ALREADY
            else:
                user.set_active(True)
                response = self.SUB_SUCCESS
            response += self.SUB_APPENDIX

            send_message(user, response)

        elif is_command('unsubscribe') or is_command('stop') or is_command('off'):
            if not user.is_active():
                response = self.UNSUB_ALREADY
            else:
                user.set_active(False)
                response = self.UNSUB_SUCCESS
            response += self.UNSUB_APPENDIX

            send_message(user, response)

        elif is_command('settings'):
            if user.is_active():
                response = self.SETTINGS_SUB
            else:
                response = self.SETTINGS_UNSUB

            send_message(user, response, markdown=True)

        elif is_command('help'):
            response = self.HELP.format(actual_name)
            if user.is_active():
                response += self.CMD_LIST_UNSUB
            else:
                response += self.CMD_LIST_SUB
            response += '\n\n' + self.HELP_LINK

            send_message(user, response, disable_web_page_preview=True)

        elif is_command('feedback'):
            response = self.FEEDBACK_STRING

            send_message(user, response, force_reply=True)

        else:
            logging.info(LOG_UNRECOGNISED)
            if user.is_group() and '@lljbot' not in cmd:
                return

            response = self.UNRECOGNISED.format(actual_name)
            if user.is_active():
                response += self.CMD_LIST_UNSUB
            else:
                response += self.CMD_LIST_SUB

            send_message(user, response)

class SendPage(webapp2.RequestHandler):
    def run(self):
        query = User.all()
        query.filter('active =', True)
        query.filter('last_auto <', get_today_time())

        devo = get_devo()
        if devo == None:
            return False
        elif devo.startswith('Sorry'):
            devo = get_devo_old()
            if devo == None:
                return False

        try:
            for user in query.run(batch_size=500):
                send_message(user, devo, msg_type='daily', markdown=True)
        except Exception as e:
            logging.warning(LOG_ERROR_DAILY + str(e))
            return False

        return True

    def get(self):
        if self.run() == False:
            taskqueue.add(url='/send')

    def post(self):
        if self.run() == False:
            self.abort(502)

class PromoPage(webapp2.RequestHandler):
    def get(self):
        taskqueue.add(url='/promo')

    def post(self):
        three_days_ago = datetime.now() - timedelta(days=3)
        query = User.all()
        query.filter('promo =', False)
        query.filter('created <', three_days_ago)
        for user in query.run(batch_size=500):
            name = user.first_name.encode('utf-8', 'ignore').strip()
            if user.is_group():
                promo_msg = 'Hello, friends in {}! Do you find LLJ Bot useful?'.format(name)
            else:
                promo_msg = 'Hi {}, do you find LLJ Bot useful?'.format(name)
            promo_msg += ' Why not rate it on the bot store (you don\'t have to exit' + \
                         ' Telegram)!\nhttps://telegram.me/storebot?start=lljbot'
            send_message(user, promo_msg, msg_type='promo')

class MessagePage(webapp2.RequestHandler):
    def post(self):
        params = json.loads(self.request.body)
        msg_type = params.get('msg_type')
        data = params.get('data')
        uid = str(json.loads(data).get('chat_id'))
        user = get_user(uid)

        try:
            result = telegram_post(data, 4)
        except Exception as e:
            logging.warning(LOG_ERROR_SENDING.format(msg_type, uid, user.get_description(), str(e)))
            logging.debug(data)
            self.abort(502)

        response = json.loads(result.content)

        if handle_response(response, user, uid, msg_type) == False:
            logging.debug(data)
            self.abort(502)

# class PhotoPage(webapp2.RequestHandler):
#     def post(self):
#         uid = self.request.body
#         user = get_user(uid)

#         build = {
#             'chat_id': uid,
#             'photo': 'AgADBQAD0agxGwgAAcgBjTgu4ZTCQJCCVb4yAARl_44G6ouSJaWxAAIC'
#         }
#         data = json.dumps(build)

#         try:
#             result = telegram_photo(data, 4)
#         except Exception as e:
#             logging.warning(LOG_ERROR_SENDING.format('Photo', uid, user.get_description(), str(e)))
#             logging.debug(data)
#             self.abort(502)

#         response = json.loads(result.content)

#         if handle_response(response, user, uid, 'photo') == False:
#             logging.debug(data)
#             self.abort(502)

class MassPage(webapp2.RequestHandler):
    def get(self):
        taskqueue.add(url='/mass')

    def post(self):
        # try:
        #     query = User.all()
        #     for user in query.run(batch_size=3000):
        #         uid = str(user.get_uid())
        #         name = user.first_name.encode('utf-8', 'ignore').strip()
        #         mass_msg = '_"The Son of God became a man to enable men to become sons of God." - C.S. Lewis_\n\n'
        #         if user.is_group():
        #             mass_msg += 'Merry Christmas, friends in {}!'.format(name)
        #         else:
        #             mass_msg += 'Merry Christmas, {}!'.format(name)
        #         mass_msg += ' ' + u'\U0001F389\U0001F384\U0001F381'.encode('utf-8', 'ignore') + \
        #                     ' Jesus is the reason for the season, and _you_ are the reason why Jesus came!'

        #         send_message(user, mass_msg, msg_type='mass', markdown=True)

        # except Exception as e:
        #     logging.error(e)
        pass

class VerifyPage(webapp2.RequestHandler):
    def get(self):
        try:
            query = User.all()
            query.filter('active =', False)
            for user in query.run(batch_size=3000):
                uid = str(user.get_uid())
                taskqueue.add(url='/verify', payload=uid)
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write('Cleanup in progress\n')
        except Exception as e:
            logging.error(e)

    def post(self):
        uid = self.request.body
        user = get_user(uid)

        try:
            result = telegram_query(uid, 4)
        except Exception as e:
            logging.warning(LOG_ERROR_QUERY.format(uid, user.get_description(), str(e)))
            self.abort(502)

        response = json.loads(result.content)
        if response.get('ok') == True:
            logging.info(LOG_USER_REACHABLE.format(uid, user.get_description()))
        else:
            error_description = str(response.get('description'))
            if error_description == RECOGNISED_ERROR_MIGRATE:
                new_uid = response.get('parameters', {}).get('migrate_to_chat_id')
                if new_uid:
                    user = user.migrate_to(new_uid)
                    logging.info(LOG_USER_MIGRATED.format(uid, new_uid, user.get_description()))
            elif error_description in RECOGNISED_ERRORS:
                user_description = user.get_description()
                user.delete()
                logging.info(LOG_USER_DELETED.format(uid, user_description))
            else:
                logging.warning(LOG_USER_UNREACHABLE.format(uid, user.get_description(), error_description))
                self.abort(502)

app = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/' + TOKEN, LljPage),
    ('/send', SendPage),
    ('/message', MessagePage),
    ('/promo', PromoPage),
    ('/mass', MassPage),
    ('/verify', VerifyPage),
    # ('/photo', PhotoPage),
], debug=True)
