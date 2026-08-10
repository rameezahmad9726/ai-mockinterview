import os
import glob
import cv2

def analyze_face_presence(frames_dir: str, fps: int = 1):
    frame_paths = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))
    if not frame_paths:
        return []

    raw_flags = []
    
    f_cas_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    p_cas_path = cv2.data.haarcascades + 'haarcascade_profileface.xml'
    
    f_cascade = cv2.CascadeClassifier(f_cas_path)
    p_cascade = cv2.CascadeClassifier(p_cas_path)

    if f_cascade.empty():
        print("[WARN] OpenCV Haar cascade XML unavailable.")
        return []

    for idx, frame_path in enumerate(frame_paths):
        img = cv2.imread(frame_path)
        if img is None:
            continue

        num_faces = 1
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            ff = f_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(35, 35))
            pf = p_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(35, 35)) if not p_cascade.empty() else []
            
            boxes = list(ff) + list(pf)
            if not p_cascade.empty():
                flipped = cv2.flip(gray, 1)
                pf_flip = p_cascade.detectMultiScale(flipped, scaleFactor=1.1, minNeighbors=4, minSize=(35, 35))
                for (x, y, w, h) in pf_flip:
                    boxes.append((gray.shape[1] - x - w, y, w, h))

            if boxes:
                merged, _ = cv2.groupRectangles(boxes + boxes, 1, 0.3)
                num_faces = len(merged)
            else:
                num_faces = 0
        except Exception:
            num_faces = 1

        at_sec = float(idx) / float(fps)
        
        if num_faces == 0:
            raw_flags.append({"kind": "no_face", "at_sec": at_sec})
        elif num_faces > 1:
            raw_flags.append({"kind": "multi_face", "at_sec": at_sec, "count": int(num_faces)})

    if not raw_flags:
        return []

    # Group contiguous flags
    grouped = []
    current_kind = None
    start_sec = 0
    last_sec = 0
    max_count = 0
    
    for f in raw_flags:
        kind = f["kind"]
        sec = f["at_sec"]
        
        if kind == current_kind and sec - last_sec <= (1.0 / fps) * 2.0:
            last_sec = sec
            if kind == "multi_face":
                max_count = max(max_count, f.get("count", 0))
        else:
            if current_kind is not None:
                meta = {"duration": round(last_sec - start_sec + (1.0 / fps), 1)}
                if current_kind == "multi_face":
                    meta["max_faces"] = max_count
                grouped.append({
                    "kind": current_kind,
                    "at_sec": round(start_sec, 1),
                    "meta": meta
                })
            current_kind = kind
            start_sec = sec
            last_sec = sec
            max_count = f.get("count", 0) if kind == "multi_face" else 0
            
    if current_kind is not None:
        meta = {"duration": round(last_sec - start_sec + (1.0 / fps), 1)}
        if current_kind == "multi_face":
            meta["max_faces"] = max_count
        grouped.append({
            "kind": current_kind,
            "at_sec": round(start_sec, 1),
            "meta": meta
        })
        
    filtered = [g for g in grouped if g["meta"]["duration"] >= 1.0]
    return filtered


