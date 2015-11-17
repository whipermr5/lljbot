import webapp2
from lljbot import User

class AdminPage(webapp2.RequestHandler):
    def get(self):
        def prep_str(str):
            if str == None:
                return '-'
            return str.encode('ascii', 'ignore')

        def prep_date(date):
            return date.strftime("%d/%m/%y %H:%M")

        query = User.all()
        query.order('-created')
        self.response.headers['Content-Type'] = 'text/html'
        self.response.write('<table>')
        self.response.write('<tr><td>#</td><td>uid</td><td>first</td><td>last</td><td>username</td>' +
                            '<td>created</td><td>received</td><td>sent</td><td>active</td></tr>\n')
        result = query.run()
        i = query.count()
        for user in result:
            uid = prep_str(user.key().name())
            fname = prep_str(user.first_name)
            lname = prep_str(user.last_name)
            uname = prep_str(user.username)
            ctime = prep_date(user.created)
            rtime = prep_date(user.last_received)
            stime = prep_date(user.last_sent)
            active = user.active
            self.response.write(('<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td>' +
                                '<td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>\n')
                                .format(i, uid, fname, lname, uname, ctime, rtime, stime, active))
            i -= 1
        self.response.write('</table>')

app = webapp2.WSGIApplication([
    ('/admin', AdminPage),
], debug=True)