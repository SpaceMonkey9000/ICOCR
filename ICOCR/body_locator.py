"""Conservative geometric component-body proposals. No trained model or package ID."""
import time
import cv2
import numpy as np


def _polygon_mask(shape, box):
    mask = np.zeros(shape[:2], np.uint8)
    cv2.fillConvexPoly(mask, np.round(box).astype(np.int32), 255)
    return mask


def overlap_fraction(box, body):
    polygon = cv2.convexHull(np.asarray(box, np.float32))
    area = abs(cv2.contourArea(polygon))
    if area <= 0:
        return 0.
    overlap, _ = cv2.intersectConvexConvex(polygon, cv2.convexHull(np.asarray(body,np.float32)))
    return float(overlap / area)


def locate_body(image):
    """Return a fully visible, central rectangular body, or a fallback reason.

    Scores are heuristic ranks, not calibrated probabilities. Clipped bodies,
    weak contrast and similarly ranked targets intentionally retain the full ROI.
    """
    started = time.perf_counter()
    result = dict(status='fallback', reason='No reliable body outline', box=None, score=0.)
    h,w = image.shape[:2]
    if min(h,w) < 64:
        result['reason'] = 'Selection too small for body detection'
        result['milliseconds'] = (time.perf_counter()-started)*1000
        return result
    scale = min(1.,640/max(h,w))
    small = cv2.resize(image,(round(w*scale),round(h*scale)),interpolation=cv2.INTER_AREA)
    sh,sw = small.shape[:2]
    gray = cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray,(5,5),0)
    edges = cv2.Canny(blurred,35,100)
    edges = cv2.morphologyEx(edges,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    _, binary = cv2.threshold(blurred,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    # Both polarities support dark plastic, light ceramic and varying PCB colours.
    saturation = cv2.cvtColor(small,cv2.COLOR_BGR2HSV)[:,:,1]
    _, colour_mask = cv2.threshold(saturation,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    colour_mask = cv2.morphologyEx(colour_mask,cv2.MORPH_OPEN,np.ones((5,5),np.uint8))
    colour_mask = cv2.morphologyEx(colour_mask,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
    lab = cv2.cvtColor(small,cv2.COLOR_BGR2LAB)
    lab_blurred = cv2.GaussianBlur(lab,(5,5),0)
    masks = [edges,binary,255-binary,colour_mask]
    # Suppress bright solder/silkscreen while proposing neutral plastic against
    # a coloured PCB. Multiple saturation cuts tolerate lighting variation.
    dark_limit = np.percentile(gray,65)
    for limit in (40,80,120):
        neutral = ((saturation < limit) & (gray < dark_limit)).astype(np.uint8)*255
        neutral = cv2.morphologyEx(neutral,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
        neutral = cv2.morphologyEx(neutral,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
        masks.append(neutral)
    candidates = []
    rejected = {}
    def reject(reason):
        rejected[reason] = rejected.get(reason,0)+1
    for mask in masks:
        contours,_ = cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        # Bound work on textured/noisy boards; small contours cannot qualify.
        contours = sorted(contours,key=cv2.contourArea,reverse=True)[:64]
        for contour in contours:
            area = abs(cv2.contourArea(contour))
            # Wide microscope selections can leave the IC at only 4-5% of ROI.
            if not .02*sh*sw <= area <= .88*sh*sw:
                continue
            rect = cv2.minAreaRect(contour)
            rw,rh = rect[1]
            if min(rw,rh) < 22 or max(rw,rh)/min(rw,rh) > 6:
                reject('size_or_aspect')
                continue
            rectangularity = area/max(1,rw*rh)
            if rectangularity < .78:
                reject('non_rectangular')
                continue
            box = cv2.boxPoints(rect)
            if (box[:,0].min()<4 or box[:,1].min()<4 or
                    box[:,0].max()>sw-5 or box[:,1].max()>sh-5):
                reject('touching_selection')
                continue
            centre = np.asarray(rect[0])
            distance = float(np.linalg.norm((centre-[sw/2,sh/2])/[sw/2,sh/2]))
            if distance > .65:
                reject('off_centre')
                continue
            inside = _polygon_mask(gray.shape, centre+(box-centre)*.86)
            outer = _polygon_mask(gray.shape, centre+(box-centre)*1.12)
            body = _polygon_mask(gray.shape,box)
            ring = (outer!=0)&(body==0)
            if np.count_nonzero(ring)<40:
                reject('insufficient_border')
                continue
            contrast = float(np.linalg.norm(np.median(lab[inside!=0],axis=0)-
                                            np.median(lab[ring],axis=0)))
            if contrast < 18:
                reject('weak_contrast')
                continue
            # Specular glare on a package top is a bright, featureless band that
            # can look like a small rectangular body. Real bodies are not
            # near-white with almost no texture and brighter than their border.
            inner_l = lab[inside!=0][:,0].astype(float)
            ring_l = float(np.median(lab[ring][:,0]))
            if (np.median(inner_l) >= 170 and np.median(inner_l)-ring_l >= 25 and
                    np.std(inner_l) < 14):
                reject('glare')
                continue
            # Require a real colour/luminance change along at least three sides,
            # not just a rectangular arrangement of disconnected text strokes.
            support = []
            for i in range(4):
                a,b = box[i],box[(i+1)%4]
                points = a+(b-a)*np.linspace(.1,.9,24)[:,None]
                toward = centre-points
                toward /= np.maximum(np.linalg.norm(toward,axis=1)[:,None],1.)
                delta = max(2.,min(rw,rh)*.035)
                inner = np.round(points+toward*delta).astype(int)
                outside = np.round(points-toward*delta).astype(int)
                inner[:,0]=np.clip(inner[:,0],0,sw-1);inner[:,1]=np.clip(inner[:,1],0,sh-1)
                outside[:,0]=np.clip(outside[:,0],0,sw-1);outside[:,1]=np.clip(outside[:,1],0,sh-1)
                differences = np.linalg.norm(lab_blurred[inner[:,1],inner[:,0]].astype(float)-
                                             lab_blurred[outside[:,1],outside[:,0]].astype(float),axis=1)
                support.append(float(np.mean(differences>=12)))
            if sum(v>=.45 for v in support)<3:
                reject('weak_edges')
                continue
            score = (.35*min(rectangularity,1.) + .30*np.mean(support) +
                     .20*min(contrast/80,1.) + .15*max(0,1-distance))
            if score < .72:
                reject('low_score')
                continue
            # Collapse duplicate threshold/edge contours of the same body.
            candidate = dict(box=box,score=float(score),contrast=contrast,
                             rectangularity=float(rectangularity))
            duplicate = next((c for c in candidates
                              if overlap_fraction(box,c['box'])>.65
                              and overlap_fraction(c['box'],box)>.65),None)
            if duplicate is not None:
                if score > duplicate['score']:
                    duplicate.update(candidate)
            else:
                candidates.append(candidate)
    candidates.sort(key=lambda c:c['score'],reverse=True)
    result['rejections'] = rejected
    result['candidate_count'] = len(candidates)
    if not candidates:
        labels = {'low_score':'Body evidence below threshold', 'weak_edges':'Body boundary incomplete',
                  'weak_contrast':'Insufficient body/background contrast',
                  'glare':'Only a glare reflection found',
                  'insufficient_border':'Insufficient surrounding border',
                  'off_centre':'Body outside selection centre',
                  'touching_selection':'Body touches selection edge',
                  'non_rectangular':'No rectangular body contour',
                  'size_or_aspect':'Body too small or too narrow'}
        result['reason'] = next((label for key,label in labels.items() if rejected.get(key)),
                                'No body-sized contour')
    if candidates:
        best = candidates[0]
        if len(candidates)>1 and best['score']-candidates[1]['score']<.07:
            result['reason'] = 'Multiple plausible bodies; tighten the selection'
        else:
            # Pixel-centre mapping accounts for rounding of the downsampled size.
            box = (best['box']+.5)*[w/sw,h/sh]-.5
            result.update(status='detected',reason='Geometric body outline',box=box.tolist(),
                          score=best['score'],contrast=best['contrast'])
    result['milliseconds'] = (time.perf_counter()-started)*1000
    return result


def body_crop(image, detection):
    """Keep original pixels inside the body; neutralise only the surrounding PCB."""
    box = np.asarray(detection.get('mask_polygon') or detection['box'],np.float32)
    h,w = image.shape[:2]
    lo = np.maximum(np.floor(box.min(axis=0)-3).astype(int),0)
    hi = np.minimum(np.ceil(box.max(axis=0)+4).astype(int),[w,h])
    x,y = lo;right,bottom = hi
    crop = image[y:bottom,x:right].copy()
    local = box-lo
    mask = _polygon_mask(crop.shape,local)
    mask = cv2.dilate(mask,np.ones((3,3),np.uint8))
    pixels = crop[mask!=0]
    if pixels.size:
        crop[mask==0] = np.median(pixels,axis=0).astype(np.uint8)
    return crop,lo.tolist()
