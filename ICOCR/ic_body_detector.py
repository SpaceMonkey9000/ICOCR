"""YOLOv8n-seg IC body inference adapter for ICOCR Qt.

All returned coordinates are full-resolution source-image pixels.  Model input
is RGB 640x640 letterbox, NCHW float32 [0,1].  Both model outputs are used:
boxes select instances, prototype masks define crop silhouettes.  Inference
is only performed on the OCR worker thread, never the preview/GUI thread.
"""
from functools import lru_cache
from pathlib import Path
import threading
import time
import cv2
import numpy as np

_SESSION_LOCK = threading.Lock()


@lru_cache(maxsize=3)
def _session(filename):
    import onnxruntime as ort
    providers = ort.get_available_providers()
    order = ['CUDAExecutionProvider', 'CPUExecutionProvider'] if 'CUDAExecutionProvider' in providers else ['CPUExecutionProvider']
    session = ort.InferenceSession(str(filename), providers=order)
    actual = session.get_providers()
    if not actual:
        raise RuntimeError('No ONNX execution provider')
    shapes = [tuple(x.shape) for x in session.get_outputs()]
    if shapes != [(1,37,8400),(1,32,160,160)]:
        raise ValueError(f'Unexpected IC body detector outputs: {shapes}')
    return session


def _letterbox(image):
    h,w = image.shape[:2]
    scale = min(640 / w, 640 / h)
    nw,nh = min(640,round(w*scale)),min(640,round(h*scale))
    x0=(640-nw)//2; y0=(640-nh)//2
    result=np.full((640,640,3),114,dtype=np.uint8)
    result[y0:y0+nh,x0:x0+nw]=cv2.resize(image,(nw,nh),interpolation=cv2.INTER_LINEAR)
    blob=np.ascontiguousarray(result[:,:,::-1].transpose(2,0,1),dtype=np.float32)[None]/255.0
    return blob,scale,x0,y0


def _mask_polygon(proto, coefficients, box, scale, left, top, width, height):
    """Make a pixel-space contour; fallback to the rectangle on tiny masks."""
    logits=np.einsum('c,chw->hw',coefficients,proto,optimize=True)
    # sigmoid threshold 0.5 is equivalent to logits > 0; resize before thresholding.
    logits=cv2.resize(logits,(640,640),interpolation=cv2.INTER_LINEAR)
    mask=(logits>0).astype(np.uint8)
    x1,y1,x2,y2=box
    ix1,iy1=max(0,int(np.floor(x1))),max(0,int(np.floor(y1)))
    ix2,iy2=min(640,int(np.ceil(x2))),min(640,int(np.ceil(y2)))
    if ix2<=ix1 or iy2<=iy1: return None
    # No other instance can leak outside this particular box.
    cropped=np.zeros_like(mask)
    cropped[iy1:iy2,ix1:ix2]=mask[iy1:iy2,ix1:ix2]
    outlines,_=cv2.findContours(cropped,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if not outlines: return None
    contour=max(outlines,key=cv2.contourArea)
    if cv2.contourArea(contour)<10: return None
    epsilon=max(1.0,0.006*cv2.arcLength(contour,True))
    contour=cv2.approxPolyDP(contour,epsilon,True).reshape(-1,2).astype(float)
    if len(contour)<3: return None
    contour[:,0]=np.clip((contour[:,0]-left)/scale,0,width-1)
    contour[:,1]=np.clip((contour[:,1]-top)/scale,0,height-1)
    return contour.tolist()



def _straight_body_polygon(mask_polygon, fallback_polygon):
    """Return a four-corner rotated rectangle fitted to a segmentation silhouette.

    Minimum-area rectangle is used rather than approximating the freeform
    contour, so rotated SOIC/QFP packages retain straight, parallel edges.
    """
    if not mask_polygon or len(mask_polygon) < 3:
        return fallback_polygon
    points = np.asarray(mask_polygon, dtype=np.float32)
    if not np.isfinite(points).all() or abs(cv2.contourArea(points)) < 16:
        return fallback_polygon
    centre, size, angle = cv2.minAreaRect(points)
    if min(size) < 2:
        return fallback_polygon
    corners = cv2.boxPoints((centre, size, angle))
    return corners.astype(float).tolist()


def detect(image, model, confidence=0.35, iou=0.45, max_detections=30, cancelled=None):
    """Return ICOCR multi_chip-compatible detections in original image pixels."""
    if cancelled and cancelled(): return []
    if image is None or image.ndim!=3 or image.shape[2]!=3: raise ValueError('Expected BGR colour frame')
    started=time.perf_counter()
    h,w=image.shape[:2]
    blob,scale,left,top=_letterbox(image)
    with _SESSION_LOCK:
        prediction, prototypes=_session(str(Path(model).resolve())).run(None,{'images':blob})
    if cancelled and cancelled(): return []
    rows=prediction[0].T
    valid=np.flatnonzero(rows[:,4]>=confidence)
    if valid.size==0: return []
    boxes=[]; scores=[]; ids=[]
    for i in valid:
        cx,cy,bw,bh=map(float,rows[i,:4])
        x1=max(0.,cx-bw/2);y1=max(0.,cy-bh/2)
        x2=min(640.,cx+bw/2);y2=min(640.,cy+bh/2)
        if x2-x1<3 or y2-y1<3: continue
        boxes.append([x1,y1,x2-x1,y2-y1]);scores.append(float(rows[i,4]));ids.append(i)
    if not boxes:return []
    kept=cv2.dnn.NMSBoxes(boxes,scores,confidence,iou)
    if len(kept)==0:return []
    found=[]; proto=prototypes[0]
    for j in np.asarray(kept).reshape(-1)[:max_detections]:
        if cancelled and cancelled():return []
        x,y,bw,bh=boxes[j]; b=[x,y,x+bw,y+bh]
        ix1=np.clip((b[0]-left)/scale,0,w-1);iy1=np.clip((b[1]-top)/scale,0,h-1)
        ix2=np.clip((b[2]-left)/scale,0,w-1);iy2=np.clip((b[3]-top)/scale,0,h-1)
        if ix2-ix1<4 or iy2-iy1<4:continue
        mask_polygon=_mask_polygon(proto,rows[ids[j],5:],b,scale,left,top,w,h)
        fallback=[[float(ix1),float(iy1)],[float(ix2),float(iy1)],
                  [float(ix2),float(iy2)],[float(ix1),float(iy2)]]
        straight=_straight_body_polygon(mask_polygon, fallback)
        found.append(dict(box=[float(ix1),float(iy1),float(ix2),float(iy2)],
                          polygon=straight,
                          mask_polygon=mask_polygon,score=scores[j],source='model',task='segment',
                          angle=0.,truncated=False,
                          milliseconds=(time.perf_counter()-started)*1000))
    return found


def for_roi(detections, roi, image_shape, *, minimum_inside=0.85):
    """Convert a full-frame detection to a local detection for read_with_body.

    Exclude truncated bodies: a partially selected chip must never cause an
    automatic masked crop.  For full-frame scans, choose the largest compatible
    detection by confidence and covered pixel area.
    """
    h,w=image_shape[:2]; x0=int(roi[0]*w);y0=int(roi[1]*h)
    x1=int(roi[2]*w);y1=int(roi[3]*h)
    valid=[]
    for d in detections:
        a,b,c,e=d['box']; area=max(0,c-a)*max(0,e-b)
        overlap=max(0,min(c,x1)-max(a,x0))*max(0,min(e,y1)-max(b,y0))
        if area<=0 or overlap/area<minimum_inside:continue
        valid.append((d['score']*area,d))
    if not valid:return None
    d=max(valid,key=lambda item:item[0])[1]
    polygon=d.get('mask_polygon') or d['polygon']
    return dict(status='detected',source='model',task='segment',
                reason='YOLOv8 IC-body segmentation',score=d['score'],
                box=(np.asarray(d['polygon'],dtype=float)-[x0,y0]).tolist(),
                mask_polygon=(np.asarray(polygon,dtype=float)-[x0,y0]).tolist(),
                milliseconds=d.get('milliseconds',0.))
