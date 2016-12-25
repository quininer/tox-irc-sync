import sys
import socket
import select
import re
import pickle
import ssl

from pytox import Tox, OperationFailedError

from time import sleep
from os.path import exists

SERVER = ['127.0.0.1', 33445, 'EDF5A5BE8DFFC1DDFAACC71A0C0FCEEDE7BED4F3FBF9C54D502BE66A297DC374']
# SERVER = ['127.0.0.1', 33445, '34922396155AA49CE6845A2FE34A73208F6FCD6190D981B1DBBC816326F26C6C']
# SERVER = ['54.199.139.199', 33445, '7F9C31FE850E97CEFD4C4591DF93FC757C7C12549DDD55F8EEAECC34FE76C029']
GROUP_BOT = '34922396155AA49CE6845A2FE34A73208F6FCD6190D981B1DBBC816326F26C6CDF3581F697E7'
PWD = ''

IRC_HOST = 'irc.freenode.net'
IRC_PORT = 6697
TOX_NAME = NAME = NICK = IDENT = REALNAME = 'toxsync-test'

CHANNEL = '#linux-cn-test'
MEMORY_DB = 'memory.pickle'

BLOCK_LIST = set()


class SyncBot(Tox):
    def __init__(self):

        self.connect()
        self.self_set_name(TOX_NAME)
        self.self_set_status_message("Send me a message with the word 'invite'")
        print('ID: %s' % self.self_get_address())

        self.readbuffer = ''
        self.tox_group_id = None

        self.irc_init()
        self.memory = {}

        if exists(MEMORY_DB):
            with open(MEMORY_DB, 'rb') as f:
                self.memory = pickle.load(f)

    def irc_init(self):
        self.irc = socket.socket()
        self.irc.connect((IRC_HOST, IRC_PORT))
        self.irc = ssl.wrap_socket(self.irc)
        if sys.version_info >= (3,0,0):
            self.irc.send(('NICK %s\r\n' % NICK).encode())
            self.irc.send(('USER %s %s bla :%s\r\n' % (IDENT, IRC_HOST, REALNAME)).encode())
        else:
            self.irc.send(('NICK %s\r\n' % NICK))
            self.irc.send(('USER %s %s bla :%s\r\n' % (IDENT, IRC_HOST, REALNAME)))

    def connect(self):
        print('connecting...')
        self.bootstrap(SERVER[0], SERVER[1], SERVER[2])

    def ensure_exe(self, func, args):
        count = 0
        THRESHOLD = 50

        while True:
            try:
                return func(*args)
            except:
                assert count < THRESHOLD
                count += 1
                for i in range(10):
                    self.iterate()
                    sleep(0.02)

    def loop(self):
        checked = False
        self.joined = False
        self.request = False

        try:
            while True:
                status = self.self_get_connection_status()
                if not checked and status:
                    print('Connected to DHT.')
                    checked = True
                    try:
                        self.bid = self.friend_by_public_key(GROUP_BOT)
                    except:
                        self.ensure_exe(self.friend_add, (GROUP_BOT, 'Hi'))
                        self.bid = self.friend_by_public_key(GROUP_BOT)

                if checked and not status:
                    print('Disconnected from DHT.')
                    self.connect()
                    checked = False

                readable, _, _ = select.select([self.irc], [], [], 0.01)

                if readable:
                    self.readbuffer += self.irc.recv(4096).decode('utf-8') if sys.version_info >= (3, 0, 0) else self.irc.recv(4096)
                    lines = self.readbuffer.split('\n')
                    self.readbuffer = lines.pop()

                    for line in lines:
                        rx = re.match(r':(.*?)!.*? PRIVMSG %s :(.*?)\r' %
                                CHANNEL, line, re.S)
                        if rx:
                            print('IRC> %s: %s' % rx.groups())
                            msg = '(%s) %s' % (rx.groups()[0], re.sub(r'\x03(?:\d{1,2}(?:,\d{1,2})?)?','',rx.groups()[1]))
                            content = rx.group(2)

                            if (
                                rx.groups()[0] in BLOCK_LIST or
                                content.split("[", 1)[-1].split("]", 1)[0] in BLOCK_LIST
                            ):
                                continue

                            if content[1:].startswith('ACTION '):
                                action = '(%s) %s' % (rx.group(1),
                                        re.sub(r'\x03(?:\d{1,2}(?:,\d{1,2})?)?','',rx.group(2)[8:-1]))
                                self.ensure_exe(self.conference_send_message,
                                        (self.tox_group_id, Tox.MESSAGE_TYPE_ACTION, action))
                            elif self.tox_group_id != None:
                                self.ensure_exe(self.conference_send_message,
                                        (self.tox_group_id, Tox.MESSAGE_TYPE_NORMAL, msg))

                            if content.startswith('^'):
                                # self.handle_command(content)
                                pass

                        l = line.rstrip().split()
                        if l[0] == 'PING':
                           self.irc_send('PONG %s\r\n' % l[1])
                        if l[1] == '376':
                            if sys.version_info >= (3,0,0):
                                self.irc.send(('PRIVMSG NickServ :IDENTIFY %s %s\r\n'
                                    % (NICK, PWD)).encode())
                                self.irc.send(('JOIN %s\r\n' % CHANNEL).encode())
                            else:
                                self.irc.send(('PRIVMSG NickServ :IDENTIFY %s %s\r\n'
                                    % (NICK, PWD)))
                                self.irc.send(('JOIN %s\r\n' % CHANNEL))

                self.iterate()
        except OperationFailedError:
            pass
        except KeyboardInterrupt:
            # TODO wait
            # self.save_to_file('data')
            pass

    def irc_send(self, msg):
        success = False
        while not success:
            try:
                if sys.version_info >= (3,0,0):
                    self.irc.send(msg.encode())
                else:
                    self.irc.send(msg)
                success = True
                break
            except socket.error:
                self.irc_init()
                sleep(1)

    def on_friend_connection_status(self, friendId, status):
        if not self.request and not self.joined \
                and friendId == self.bid and status:
            print('Groupbot online, trying to join group chat.')
            self.request = True
            self.ensure_exe(self.friend_send_message, (self.bid, Tox.MESSAGE_TYPE_NORMAL, 'invite'))

    def on_conference_invite(self, friendid, type, data):
        if not self.joined:
            self.joined = True
            self.tox_group_id = self.conference_join(friendid, data)
            print('Joined groupchat.')

    def on_conference_message(self, groupnumber, friendgroupnumber, type, message):
        if type == Tox.MESSAGE_TYPE_NORMAL:
            self.on_group_message(groupnumber, friendgroupnumber, message)
        elif type == Tox.MESSAGE_TYPE_ACTION:
            self.on_group_action(groupnumber, friendgroupnumber, message)

    def on_group_message(self, groupnumber, friendgroupnumber, message):
        if message.startswith("@@"):
            return
        name = self.conference_peer_get_name(groupnumber, friendgroupnumber)
        if len(name) and name != NAME:
            print('TOX> %s: %s' % (name, message))
            if message.startswith('>'):
                message = '\x0309%s\x03' % message

            for msg in message.split('\n'):
                if not msg.strip(): continue
                self.irc_send('PRIVMSG %s :(%s) %s\r\n' % (CHANNEL, name, msg))

            if message.startswith('^'):
                self.handle_command(message)

    def on_group_action(self, groupnumber, friendgroupnumber, action):
        name = self.conference_peer_get_name(groupnumber, friendgroupnumber)
        if len(name) and name != NAME:
            print('TOX> %s: %s' % (name, action))
            if action.startswith('>'):
                action = '\x0309%s\x03' % action
            self.irc_send('PRIVMSG %s :\x01ACTION (%s) %s\x01\r\n' %
                    (CHANNEL, name, action))

    def on_friend_request(self, pk, message):
        print('Friend request from %s: %s' % (pk, message))
        self.friend_add_norequest(pk)
        print('Accepted.')

    def on_friend_message(self, friendid, message):
        if message == 'invite':
            if not self.tox_group_id is None:
                print('Inviting %s' % self.get_name(friendid))
                self.invite_friend(friendid, self.tox_group_id)
                return
            else:
                message = 'Waiting for GroupBot, please try again in 1 min.'
        elif message == "Group doesn't exist.":
            message = 'group text'

        self.ensure_exe(self.friend_send_message, (friendid, Tox.MESSAGE_TYPE_NORMAL, message))
        if message == "Group doesn't exist.":
            self.ensure_exe(self.friend_send_message, (friendid, Tox.MESSAGE_TYPE_NORMAL, 'invite'))

    def send_both(self, content):
        self.ensure_exe(self.conference_send_message, (self.tox_group_id, Tox.MESSAGE_TYPE_NORMAL, content))
        self.irc_send('PRIVMSG %s :%s\r\n' % (CHANNEL, content))

    def handle_command(self, cmd):
        cmd = cmd[1:]
        if cmd in ['syncbot', 'echobot']:
#            self.send_both(self.get_address())
            pass
        elif cmd.startswith('say ') and len(cmd.split())>=1:
            args = cmd[len('say '):]
            self.send_both(args)
        elif cmd == 'resync':
            pass
            # sys.exit(0)
        elif cmd.startswith("block "):
            if len(BLOCK_LIST) <= 10:
                BLOCK_LIST.add(cmd.split(" ")[-1])
            else:
                self.send_both("block list too long.")
        elif cmd.startswith("unblock "):
            try:
                BLOCK_LIST.remove(cmd.split(" ")[-1])
            except KeyError as err:
                self.send_both("the list have no {}.".format(err))
        elif cmd.startswith("blist"):
            self.send_both("BLOCK LIST: {}".format(" | ".join(map(str, BLOCK_LIST))))
#         elif cmd.startswith('remember '):
            # args = cmd[len('remember '):].split(' ')
            # subject = args[0]
            # desc = ' '.join(args[1:])
            # self.memory[subject] = desc
            # with open(MEMORY_DB, 'wb') as f:
                # pickle.dump(self.memory, f)
            # self.send_both('Remembering ^%s: %s' % (subject, desc))
        # elif self.memory.get(cmd):
            # self.send_both(self.memory[cmd])


t = SyncBot()
t.loop()
