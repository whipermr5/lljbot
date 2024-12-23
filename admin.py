from lljbot import User
from datetime import datetime, timedelta

class AdminPage():
    def get(self):
        def prep_date(date):
            if date == None:
                return ''
            date = date + timedelta(hours=8)
            return date.strftime("%d %b %H:%M:%S")

        def prep_active(active):
            if active:
                return '\U00002714'
            else:
                return ''

        def prep_group(uid):
            if int(uid) < 0:
                return '\U00002714'
            else:
                return ''

        offset = int(self.request.get('offset', 0))
        limit = int(self.request.get('limit', 100))
        active = int(self.request.get('active', 0))
        if limit == -1:
            limit = None
        if active == 0:
            active = False
        else:
            active = True
        query = User.all()
        if active:
            query.filter('active =', True)
        query.order('-created')
        self.response.headers['Content-Type'] = 'text/html; charset=utf-8'
        self.response.write('<html>\n<head>\n<title>LLJ Bot Admin</title>\n</head>\n<body>\n' +
                            '<table border="1" style="border: 1px solid black; border-collapse: collapse; padding: 10px;">\n')
        self.response.write('<tr><th>#</th><th>Chat ID</th><th>Name</th>' +
                            '<th>Created</th><th>Last received</th><th>Last sent</th><th>Last auto</th><th>Active</th><th>Group</th></tr>\n')
        result = query.run(limit=limit, offset=offset, batch_size=5000)
        i = 1
        for user in result:
            uid = user.key().name()
            name = user.first_name
            if user.last_name:
                name += ' ' + user.last_name
            if user.username:
                name += ' @' + user.username
            ctime = prep_date(user.created)
            rtime = prep_date(user.last_received)
            stime = prep_date(user.last_sent)
            atime = prep_date(user.last_auto)
            active = prep_active(user.active)
            group = prep_group(uid)
            self.response.write(('<tr><td>{}</td><td>{}</td><td>{}</td>' +
                                '<td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>\n')
                                .format(i, uid, name, ctime, rtime, stime, atime, active, group))
            i += 1
        self.response.write('</table>\n</body>\n</html>')

class MigratePage():
    def get(self):
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write('Migrate page: running...')
        # today = (datetime.utcnow() + timedelta(hours=8)).date()
        # today_time = datetime(today.year, today.month, today.day) - timedelta(hours=8)
        # query = User.all()
        # query.filter('last_auto <', today_time)
        # for user in query.run(batch_size=1000):
        #     that_day = (user.last_auto + timedelta(hours=8)).date()
        #     that_day_time = datetime(that_day.year, that_day.month, that_day.day) - timedelta(hours=8)
        #     user.last_auto = that_day_time
        #     user.put()
        self.response.write(' done!')
        return

# app = webapp2.WSGIApplication([
#     ('/admin', AdminPage),
#     ('/migrate', MigratePage),
# ], debug=True)
