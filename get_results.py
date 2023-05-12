from datetime import datetime
from pymongo import MongoClient
import random
import sys




client = MongoClient()
db = client.lsc.session
db2 = client.lsc.query
SECONDS_PER_CLUE = 30
SECONDS_LAST_CLUE = 150
MAX_POINT = 100
MAX_POINT_TASK_END = 50
PENALTY_PER_WRONG = 10

class Query():
    def __init__(self, idx, text=[], results=[]):
        self.idx = idx
        existed = db2.find_one({"idx": idx})
        if existed:
            self.restore_from_dict(existed)
        else:
            self.id = None
            self.text = text # ["Default Query 1", "Default Query 2", "Default Query 3"]
            self.time = [SECONDS_PER_CLUE for i in range(len(text) - 1)] + [SECONDS_LAST_CLUE] 
            self.results = results # ["image1", "image2", "image3"]
            self.current = 0
            self.starttime = None
            self.finished = False  
            self.write_to_db()  
            
    def at_final_clue(self):
        return self.current == len(self.text) - 1
    
    def restore_from_dict(self, dictdata):
        self.text = dictdata["text"]
        self.results = dictdata["results"]
        self.current = dictdata["current"]
        self.idx = dictdata["idx"]
        self.id = dictdata["_id"]

    def to_dict(self):
        return {"text": self.text, 
                "results": self.results, 
                "current": self.current}
    
    def get_current_text(self):
        return self.text[self.current], self.time[self.current]

    def restart(self):
        self.current = 0
        self.write_to_db()
    
    def next_clue(self):
        self.current += 1
        self.write_to_db()
        if self.current >= len(self.text):
            return False
        return True
    
    def finish_clue(self):
        self.current = len(self.text) - 1
        self.finished = True
        self.write_to_db()

    def eval(self, imageid):
        return imageid in self.results

    def write_to_db(self):
        if self.id:
            db2.update_one({'_id' : self.id}, {'$set': self.to_dict()})
        else:
            self.id = db2.insert_one(self.to_dict()).inserted_id

def get_all_queries(filename):
    query_id = None
    text = []
    results = []
    queries = {}
    with open(filename) as f:
        for line in f.readlines():
            line = line.strip()
            if not line:
                if query_id:
                    queries[query_id] = Query(query_id, text, results)
                query_id = None
                text = []
                results = []
                continue
            if len(line) == 2:
                query_id = int(line)
            elif line.startswith("LSC"):
                query_id = int(line.split('-')[-1])
            else:
                if len(text) < 6:
                    text.append(line.strip().replace('. ', '.\n'))
                else:
                    results.append(line.strip())
    if query_id:
        queries[query_id] = Query(query_id, text, results)
    return queries

ALL_QUERIES = get_all_queries('backend/queries/lsc22.txt')
print("All queries:", ALL_QUERIES.keys())
# TEST_QUERIES = [73, 66, 62]
# EXP_QUERIES = [72, 64, 57, 63, 74]
TEST_QUERIES = [108, 109, 110]
EXP_QUERIES = [key for key in ALL_QUERIES.keys() if key not in TEST_QUERIES]
random.shuffle(EXP_QUERIES)

class LSCSession():
    def __init__(self, name):
        self.name = name
        existed = db.find_one({"name": name})
        if existed:
            self.restore_from_dict(existed)
        else:
            self.time = 0
            self.submissions = [[] for i in range(len(EXP_QUERIES))]
            self.id = None
            if "test" in name.lower():
                self.query_ids = TEST_QUERIES
            else:
                self.query_ids = EXP_QUERIES
            self.query_id = 0
            self.scores = [0 for i in range(len(EXP_QUERIES))]
            self.write_to_db()

    def reset(self):
        self.time = 0
        self.submissions = [[] for i in range(len(EXP_QUERIES))]
        self.id = None
        if "test" in self.name.lower():
            self.query_ids = TEST_QUERIES
        else:
            self.query_ids = EXP_QUERIES
        self.query_id = 0
        self.scores = [0 for i in range(len(EXP_QUERIES))]
        self.write_to_db()

    def add_submission(self, imageid):
        current_query = self.get_current_query()
        correctness = current_query.eval(imageid)
        current_id = current_query.current
        submission_time = current_query.time[current_id] - self.time
        if current_id > 0:
            past_time = sum(current_query.time[:current_id])
        else:
            past_time = 0
        # print("Client-side:", submission_time + past_time, "Server-side:", timecounter.time() - current_query.starttime)
        self.submissions[self.query_id].append((imageid, correctness, submission_time + past_time))
        self.get_score()
        if correctness:
            self.get_current_query().finish_clue()
        self.write_to_db()
        return correctness

    def set_time(self, time):
        self.time = float(time)
        self.write_to_db()

    def get_score(self):
        submissions = self.submissions[self.query_id]
        duration = sum(self.get_current_query().time)
        correctness = [sub[1] for sub in submissions]
        if True in correctness:
            first_correct = correctness.index(True)
            time_fraction = 1 - min(1.0, submissions[first_correct][2] / duration)
            self.scores[self.query_id] = max(0, MAX_POINT_TASK_END + ((MAX_POINT - MAX_POINT_TASK_END) * time_fraction) - (first_correct * PENALTY_PER_WRONG))
        self.write_to_db()

    def get_current_query(self):
        try:
            return ALL_QUERIES[self.query_ids[self.query_id]]
        except IndexError as e:
            return None
    
    def get_current_score(self):
        if self.query_id < len(self.scores):
            return round(self.scores[self.query_id], 2)
        print(self.query_id, self.scores)
        return 0

    def get_total_score(self):
        return round(sum(self.scores), 2)

    def restore_from_dict(self, dictdata):
        self.name = dictdata["name"]
        self.time = dictdata["time"]
        self.scores = dictdata["scores"]
        self.submissions = dictdata["submissions"]
        self.query_ids = dictdata["query_ids"]
        self.query_id = dictdata["query_id"]
        self.id = dictdata["_id"]

    def to_dict(self):
        return {"name": self.name, 
                "time": self.time, 
                "scores": self.scores, 
                "submissions": self.submissions, 
                "query_ids": self.query_ids,
                "query_id": self.query_id}

    def next_query(self):
        self.time = 0
        self.query_id += 1
        self.write_to_db()
        if self.query_id >= len(self.query_ids):
            return False
        return True

    def write_to_db(self):
        if self.id:
            db.update_one({'_id' : self.id}, {'$set': self.to_dict()})
        else:
            self.id = db.insert_one(self.to_dict()).inserted_id
    

def get_score(session_name):
    session = LSCSession(session_name)
    print(session.submissions)
    print("Scores")
    scores = [round(score, 2) for score in session.scores]
    print(scores)
    print("Image scores:", sum([scores[i] for i in [1,2,3,4]]))
    print("Scene scores:", sum([scores[i] for i in [0,5,6,7]]))
    print("Total:", session.get_total_score())
    for i, query in enumerate(session.submissions):
        done = False
        for j, sub in enumerate(query):
            if sub[1]:
                print(i + 1, j, sub[2], scores[i])    
                done = True
        if not done:
            print(i + 1, len(query), "N/A", scores[i])

if __name__ == "__main__":
    session_name = sys.argv[1]
    if session_name != "mysceal":
        print("Getting stats for session", session_name)
        get_score(session_name)
        try:
            to_delete = sys.argv[2]
            if to_delete == "del":
                session = LSCSession(session_name)
                session.detete()
        except IndexError as e:
            pass
    else:
        mysession = LSCSession("mysceal")
        mysession.submissions = [[["", True, 37]], [["", True, 158]], [
            ["", True, 90]], [["", False, 79], ["", True, 82]], []]
        for i in range(5):
            mysession.query_id = i
            mysession.get_score()
        print("Scores")
        print([round(score, 2) for score in mysession.scores])
        print("Total:", mysession.get_total_score())
    


# Coni
# [[['b00002411_21i6bq_20150319_162318e', True, 54]], 
# [['b00000511_21i6bq_20150307_114813e', True, 325]], 
# [['B00012345_21I6X0_20180523_152443E', True, 335]], [], []]
# Scores
# [92.5, 54.86, 53.47, 0, 0]
# Total: 200.83
# 
# Florian
# [[['b00002412_21i6bq_20150319_162319e', True, 37]], 
# [['20160917_130458_000', False, 140], 
# ['b00000507_21i6bq_20150307_114541e', True, 283]], 
# [], 
# [['b00000077_21i6bq_20150228_071546e', True, 162]], []]
# Scores
# [94.86, 50.69, 0, 77.5, 0]
# Total: 223.06

# Nhu_Exp_1
# [[['b00002413_21i6bq_20150319_162320e', True, 108]], 
# [['b00000506_21i6bq_20150307_114508e', True, 226]], 
# [], 
# [['b00000072_21i6bq_20150228_071542e', True, 352]], 
# []]
# Scores
# [85.0, 68.61, 0, 51.11, 0]
# Total: 204.72

# Khiem_exp_1
# [[['b00002366_21i6bq_20150316_152935e', False, 11], 
# ['b00002410_21i6bq_20150319_162318e', True, 23]], 
# [['20161002_133656_000', False, 117], ['20160917_130458_000', False, 128], ['b00000506_21i6bq_20150307_114508e', True, 237]],
# [['20160906_212416_000', False, 30], ['B00012345_21I6X0_20180523_152443E', True, 264]], 
# [], 
# []]
# Scores
# [86.81, 47.08, 53.33, 0, 0]
# Total: 187.22

# Tu_Exp1
# [[['b00002412_21i6bq_20150319_162319e', True, 13]], 
# [['b00000518_21i6bq_20150307_115233e', True, 295]], 
# [], 
# [['b00000072_21i6bq_20150228_071542e', True, 342]], 
# []]
# Scores
# [98.19, 59.03, 0, 52.5, 0]
# Total: 209.72

# Getting stats for session An
# [[['b00002411_21i6bq_20150319_162318e', True, 87]], 
# [['b00000506_21i6bq_20150307_114508e', True, 303]], 
# [], 
# [], 
# []]
# Scores
# [87.92, 57.92, 0, 0, 0]
# Total: 145.83

# Getting stats for session Diem
# [[['b00002410_21i6bq_20150319_162318e', True, 67]], 
# [['b00000492_21i6bq_20150307_114114e', False, 298], ['b00000506_21i6bq_20150307_114508e', True, 336]], 
# [['20160906_215143_000', False, 292]], 
# [['b00000079_21i6bq_20150228_071547e', True, 256]], 
# []]
# Scores
# [90.69, 43.33, 0, 64.44, 0]
# Total: 198.47

# MySceal
# [[[True, 37]], [[True, 158]], [[True, 90]], [[False, 79], [True, 82]], []] 
# [94.86, 78.06, 87.5, 78.61, 0]
# Total: 339.03
