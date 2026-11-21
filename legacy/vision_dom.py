import cv2
import json
from collections import deque, Counter
from ultralytics import YOLO

# 1. 加载你自己训练的.pt权重
model = YOLO("yolov8n.pt")  # 你的.pt权重文件名

N = 5  # 用于平滑的最近帧数
last_n_results = deque(maxlen=N)

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
while True:
    ret, frame = cap.read()
    if not ret:
        break

    results = model(frame)
    preds = results[0]
    boxes = preds.boxes
    names = preds.names

    # 2. 只保留高置信度检测结果
    current_tiles = []
    for box in boxes:
        conf = float(box.conf[0])
        if conf < 0.5:
            continue
        cls_id = int(box.cls[0])
        cls_name = names[cls_id]
        current_tiles.append(cls_name)

    last_n_results.append(tuple(current_tiles))

    # 3. 多帧投票平滑
    merged = sum([Counter(result) for result in last_n_results], Counter())
    smooth_tiles = [tile for tile, count in merged.items() if count >= N // 2]

    print("当前平滑后识别手牌：", smooth_tiles)

    # 4. 可视化输出
    annotated_frame = results[0].plot()
    cv2.imshow("Mahjong YOLOv8 Local", annotated_frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('s'):
        with open("east_hand.json", "w", encoding="utf-8") as f:
            json.dump(smooth_tiles, f, ensure_ascii=False, indent=2)
        print("已保存当前手牌到 east_hand.json：", smooth_tiles)

cap.release()
cv2.destroyAllWindows()
