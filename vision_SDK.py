import cv2
import json
from inference_sdk import InferenceHTTPClient
from collections import deque, Counter

client = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key="9U8KIimn1UZTXGWrxXgX"
)

N = 5  # 最近5帧
last_n_results = deque(maxlen=N)

with client.use_model(model_id="mahjong-vtacs/1"):
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        preds = client.infer(frame)
        # ---- 增加x坐标排序，保证手牌顺序从左到右 ----
        tile_boxes = []
        for p in preds.get("predictions", []):
            if p["confidence"] < 0.5:
                continue
            x, y, w, h = map(int, (p["x"], p["y"], p["width"], p["height"]))
            cls = p["class"]
            tile_boxes.append((x, cls))
        tile_boxes.sort(key=lambda x: x[0])
        current_tiles = [cls for x, cls in tile_boxes]
        last_n_results.append(tuple(current_tiles))

        # 多帧投票
        merged = sum([Counter(result) for result in last_n_results], Counter())
        smooth_tiles = [tile for tile, count in merged.items() if count >= N // 2]

        print("当前平滑后识别手牌（从左到右）：", smooth_tiles)

        # 可视化
        for p in preds.get("predictions", []):
            if p["confidence"] < 0.5:
                continue
            x, y, w, h = map(int, (p["x"], p["y"], p["width"], p["height"]))
            cls, conf = p["class"], p["confidence"]
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0,255,0), 2)
            cv2.putText(frame, f"{cls} {conf:.2f}",
                        (x, y-5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)

        cv2.imshow("Mahjong Local Inference", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            with open("east_hand.json", "w", encoding="utf-8") as f:
                json.dump(smooth_tiles, f, ensure_ascii=False, indent=2)
            print("已保存当前手牌到 east_hand.json：", smooth_tiles)

    cap.release()
    cv2.destroyAllWindows()
