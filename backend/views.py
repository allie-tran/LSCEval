from django.http import JsonResponse
from datetime import datetime
from pymongo import MongoClient
import random
from django.views.decorators.csrf import csrf_exempt
import time as timecounter
import copy

client = MongoClient()
db = client.lsc.session
db.drop()
db = client.lsc.session
db2 = client.lsc.query
# db2.drop()
# db2 = client.lsc.query
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
        return f"Query {self.idx}:\n" + self.text[self.current], self.time[self.current]

    def restart(self):
        self.current = 0
        self.finished = False  
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
TEST_QUERIES = [108, 109, 110, 119, 120, 121]
EXP_QUERIES = [key for key in ALL_QUERIES.keys() if key not in TEST_QUERIES][:8]

LATIN_SQUARE = ["A	A	A	A	B	B	B	B",
                "A	A	A	B	B	B	B	A",
                "A	A	B	B	B	B	A	A",
                "A	B	B	B	B	A	A	A",
                "B	B	B	B	A	A	A	A",
                "B	B	B	A	A	A	A	B",
                "B	B	A	A	A	A	B	B", 
                "B	A	A	A	A	B	B	B"]

class LSCSession():
    def __init__(self, name):
        self.name = name
        existed = db.find_one({"name": name})
        self.all_queries = ALL_QUERIES
        if existed:
            self.restore_from_dict(existed)
        else:
            self.time = 0
            self.id = None
            if "test" in name.lower():
                self.query_ids = TEST_QUERIES[:3]
            elif "test2" in name.lower():
                self.query_ids = random.choices(TEST_QUERIES, k=3)
            elif "user" in name.lower():
                self.query_ids = EXP_QUERIES
            else:
                self.query_ids = random.choices(EXP_QUERIES, k=8)
            for query in self.query_ids:
                ALL_QUERIES[query].restart()
            self.query_id = 0
            self.submissions = [[] for i in range(len(self.query_ids))]
            self.scores = [0 for i in range(len(self.query_ids))]
            self.write_to_db()

    def reset(self):
        self.time = 0
        if "test" in self.name.lower():
            self.query_ids = TEST_QUERIES
        elif "test2" in self.name.lower():
            self.query_ids = random.choices(TEST_QUERIES, k=3)
        elif "user" in self.name.lower():
            self.query_ids = EXP_QUERIES
        else:
            self.query_ids = random.choices(EXP_QUERIES, k=8)
        for query in self.query_ids:
            ALL_QUERIES[query].restart()
        self.query_id = 0
        self.submissions = [[] for i in range(len(self.query_ids))]
        self.scores = [0 for i in range(len(self.query_ids))]
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
            print(e)
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
    

def jsonize(response):
    # JSONize
    response = JsonResponse(response)
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    response["Access-Control-Allow-Credentials"] = "true"
    response["Access-Control-Allow-Headers"] = "X-Requested-With, Content-Type"
    return response

@csrf_exempt
def new_session(request):
    session_name = request.GET.get("session_name")
    session = LSCSession(session_name)
    try:
        query = session.get_current_query()
        if query.finished:
            session_valid = session.next_query()
            if session_valid:
                query = session.get_current_query()
            else:
                return jsonize({"query": "The End.", "score": session.get_current_score(), "total_score": session.get_total_score()})
        query.restart()
        text, time = query.get_current_text()
        return jsonize({"query": text, "time": time, 
                        "score": session.get_current_score(), "total_score": session.get_total_score()})
    except IndexError:
        return jsonize({"query": "The End.", "score": session.get_current_score(), "total_score": session.get_total_score()})

@csrf_exempt
def end_query_round(request):
    session_name = request.GET.get("session_name")
    session = LSCSession(session_name)
    valid = session.next_query()
    if valid:
        query = session.get_current_query()
        query.restart()
        text, time = query.get_current_text()
        return jsonize({"query": text, "time": time, "score": session.get_current_score(), "total_score": session.get_total_score()})
    else:
        return jsonize({"query": "The End.", "score": session.get_current_score(), "total_score": session.get_total_score()})

@csrf_exempt
def next_clue(request):
    session_name = request.GET.get("session_name")
    session = LSCSession(session_name)
    query = session.get_current_query()
    if not query:
        return jsonize({"query": "The End.", "score": session.get_current_score(), "total_score": session.get_total_score()})
    valid = query.next_clue()
    if not valid:
        session_valid = session.next_query()
        if session_valid:
            query = session.get_current_query()
            query.restart()
            text, time = query.get_current_text()
            return jsonize({"query": text, "time": time, "new": True, "score": session.get_current_score(), "total_score": session.get_total_score()})
        else:
            return jsonize({"query": "The End.", "score": session.get_current_score(), "total_score": session.get_total_score()})
    text, time = query.get_current_text()
    return jsonize({"query": text, "time": time, "score": session.get_current_score(), "total_score": session.get_total_score()})

@csrf_exempt
def get_query(request):
    session_name = request.GET.get('session_name')
    session = LSCSession(session_name)
    return jsonize({"query": [ALL_QUERIES[idx].text for idx in session.query_ids]})

@csrf_exempt
def submit(request):
    session_name = request.GET.get('session')
    session = LSCSession(session_name)
    if session is None:
        return jsonize({"description": "Unauthorized"})
    item = request.GET.get('item')
    correctness = session.add_submission(item)
    return jsonize({"description": "Correct" if correctness else "Incorrect"})

@csrf_exempt
def get_score(request):
    global start
    session_name = request.GET.get('session_name')
    current_time = request.GET.get('time')
    session = LSCSession(session_name)
    if current_time == "30":
        session.get_current_query().starttime = timecounter.time()
    session.set_time(current_time)
    return jsonize({"score": session.get_current_score(), "total_score": session.get_total_score()})


@csrf_exempt
def reset(request):
    session_name = request.GET.get('session_name')
    session = LSCSession(session_name)
    session.reset()
    return jsonize({"description": "Success", "total_score": session.get_total_score()})