# import sys
# import os
# sys.path.insert(1,os.path.abspath("./pyzk"))
# from zk import ZK, const
# from zk import ZK, const
# import datetime
# conn = None
# import os
# zk = ZK('192.168.1.13', port=4370, timeout=5)
# conn = zk.connect()
# data = conn.get_attendance()
# for d in data:
#     print(d)
#     aa = str(d)
#     splis = aa.split(': ')
#     print(datetime.datetime.now())
#     date_split = splis[2].split(' (')
#     print(date_split[0])

# # conn.clear_data()
# # print(conn.get_attendance())
# # conn.clear_attendance()
# # try:
# #     print('Connecting to device ...')
# #     conn = zk.connect()
# #     print("Connection SUccess")
# #     name = input("Enter Name of User")
# #     card = input("Card No:")

# #     conn.set_user(uid=None, name=name, privilege=0, password='', group_id='', user_id='', card=card)
# #     print("User Saved Successfully")
  
# # except Exception:
# #     print("Process terminate")
# # finally:
# #     if conn:
# #         conn.disconnect()

import socket # for sockets
import sys # for exit
#—————————————————————————–
remote_ip = "192.168.1.13" # should match the instrument’s IP address
port = 4370 # the port number of the instrument service
count = 0

def SocketConnect():
    try:
        #create an AF_INET, STREAM socket (TCP)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except socket.error:
        print ('Failed to create socket.')
        sys.exit()
    try:
        #Connect to remote server
        s.connect((remote_ip , port))
        info = s.recv(4370)
        print(info)
    except socket.error:
        print ('failed to connect to ip ' + remote_ip)
        return s


SocketConnect()
