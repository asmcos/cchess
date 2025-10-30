import os
import os.path
from collections import Counter
from pprint import pprint

a = []
for parent, folders, files in os.walk("."):
    for f in files:
        _, ext = os.path.splitext(f)
        a.append(ext)
pprint(Counter(a).most_common())
"""
[('.XQF', 5790),
 ('.QP', 4000),
 ('.xqf', 3374),
 ('.SG', 48),
 ('.txt', 27),
 ('.doc', 17),
 ('.xqn', 17),
 ('.CBL', 16),
 ('', 10),
 ('.rar', 7),
 ('.bin', 6),
 ('.qp', 3),
 ('.py', 2),
 ('.exe', 2), 
 ('.jpg', 1),
 ('.HTT', 1),
 ('.ini', 1),
 ('.TXT', 1),
 ('.lib', 1),
 ('.SGM', 1),
 ('.data', 1),
 ('.hash', 1)]
"""
