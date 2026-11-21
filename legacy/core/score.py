import json
from collections import defaultdict

class ScoreRecorder:
    def __init__(self, filename="mahjong_score_log.json"):
        self.filename = filename
        self.rounds = []  # 每一局的信息组成一个list

    def record_game(self, scores, score_logs):
        """
        保存单局分数与番型信息。
        scores: {WindPosition: int}
        score_logs: {WindPosition: [ {fans, score, ...}, ... ]}
        """
        result = {
            "scores": {str(pos): score for pos, score in scores.items()},
            "score_logs": {str(pos): logs for pos, logs in score_logs.items()}
        }
        self.rounds.append(result)

    def save(self):
        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(self.rounds, f, indent=2, ensure_ascii=False)

    def load(self):
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                self.rounds = json.load(f)
        except FileNotFoundError:
            self.rounds = []

    def print_summary(self):
        # 输出所有局的最终分数
        print("\n==== Mahjong Game Score Summary ====")
        for i, game in enumerate(self.rounds):
            print(f"第{i+1}局:")
            for pos, score in game["scores"].items():
                print(f"  {pos}: {score} 分")
            print("")

    def get_total_scores(self):
        # 累计所有局的总分
        total = defaultdict(int)
        for game in self.rounds:
            for pos, score in game["scores"].items():
                total[pos] += score
        return total
