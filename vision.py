import cv2
from inference_sdk import InferenceHTTPClient
import json

client = InferenceHTTPClient(
    api_url="http://localhost:9001",
    api_key=None
)

with client.use_model(model_id="mahjong-vtacs/1"):
    latest_tiles = []
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        preds = client.infer(frame)
        latest_tiles = [p["class"] for p in preds.get("predictions", [])]
        print("当前识别到的手牌：", latest_tiles)

        for p in preds.get("predictions", []):
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
            # 按下 s 键保存当前手牌到 east_hand.json
            with open("east_hand.json", "w", encoding="utf-8") as f:
                json.dump(latest_tiles, f, ensure_ascii=False, indent=2)
            print("已保存当前手牌到 east_hand.json：", latest_tiles)

    cap.release()
    cv2.destroyAllWindows()
