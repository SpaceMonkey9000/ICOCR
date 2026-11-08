"""Video canvas rendering: frame preview, selection, tracked marking label and overlays.

Canvas items are created once and moved/reconfigured each tick (0.8.3.2), and
unchanged geometry/options are not re-sent to Tk (0.8.4.3).
"""
import time

import cv2
from PIL import Image, ImageTk

import multi_chip
from app_helpers import _UNSET, ItemPool, preview_resize
from app_presenters import overlay_label

BACKGROUND = '#101923'
STATUS_COLOUR = '#9affdc'
SELECTION_COLOUR = '#35e1b4'
BODY_COLOUR = '#57cfff'
DETECTION_COLOUR = '#ff9f43'
STATUS_BAR_HEIGHT = 62
LABEL_TOP = 68                 # labels stay below the status bar


def to_canvas(points, x, y, dw, dh, w, h):
    """Image polygon -> flat canvas coordinates of the displayed frame."""
    return [v for px, py in points for v in (x+px*dw/w, y+py*dh/h)]


class RenderMixin:
    def reset_canvas_state(self):
        """Forget every canvas item (after canvas.delete('all') or before the first draw)."""
        self._items = {}
        self._detection_items = None
        self._chip_items = None
        self._canvas_cache = {}
        self._detections_drawn = False
        self._chips_drawn = False
        self.photo = None
        self._photo_size = None
        self._message = None
        self._render_frame = None
        self._render_size = None

    def clear_canvas(self):
        self.canvas.delete('all')
        self.reset_canvas_state()

    def draw_message(self):
        """Without video, show why (opening, failed, stopped) instead of a blank canvas."""
        if self._items:
            self.clear_canvas()
        cw, ch = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        text = '\n'.join(v for v in (self.overlay, self.state.get()) if v)
        if self._message is None:
            self._message = self.canvas.create_text(cw/2, ch/2, fill=STATUS_COLOUR, justify='center',
                                                    font=('Segoe UI', 13, 'bold'))
        self.canvas.coords(self._message, cw/2, ch/2)
        self.canvas.itemconfigure(self._message, text=text, width=max(100, cw-40))

    def canvas_coords(self, item, *coords):
        """canvas.coords, skipped when the item already has these coordinates.
        Only for items that are never moved by other code (not the label)."""
        key = (item, 'coords')
        if self._canvas_cache.get(key) != coords:
            self.canvas.coords(item, *coords)
            self._canvas_cache[key] = coords

    def canvas_configure(self, item, **options):
        """canvas.itemconfigure, skipped for options the item already has."""
        cache = self._canvas_cache
        changed = {k: v for k, v in options.items() if cache.get((item, k), _UNSET) != v}
        if changed:
            self.canvas.itemconfigure(item, **changed)
            for k, v in changed.items():
                cache[(item, k)] = v

    def create_items(self, x, y, cw):
        canvas = self.canvas
        return dict(
            video=canvas.create_image(x, y, anchor='nw'),
            roi=canvas.create_rectangle(0, 0, 1, 1, outline=SELECTION_COLOUR, width=2),
            body=canvas.create_polygon(0, 0, 1, 0, 1, 1, 0, 1, fill='', outline=BODY_COLOUR, width=2,
                                       dash=(5, 3), state='hidden'),
            polygon=canvas.create_polygon(0, 0, 1, 0, 1, 1, 0, 1, fill='', width=2, state='hidden'),
            label_bg=canvas.create_rectangle(0, 0, 1, 1, fill=BACKGROUND, state='hidden'),
            label=canvas.create_text(0, 0, anchor='nw', font=('Segoe UI', 11, 'bold'), state='hidden'),
            bar=canvas.create_rectangle(0, 0, cw, STATUS_BAR_HEIGHT, fill=BACKGROUND, outline=''),
            status=canvas.create_text(14, 12, fill=STATUS_COLOUR, anchor='nw', font=('Segoe UI', 13, 'bold')))

    def draw(self):
        if self.frame is None:
            self.draw_message()
            return
        if self._message is not None:
            self.canvas.delete(self._message)
            self._message = None
        started = time.perf_counter()
        frame, row = self.display_state()
        vote = self.vote
        if row is not None and vote is not None and getattr(vote, 'view', None) is not None:
            # Tracked geometry, frame-voted reading.
            row = dict(vote.view, box=row['box'], body_box=row.get('body_box'))
        h, w = frame.shape[:2]
        cw, ch = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        scale = min(cw/w, ch/h)
        dw, dh = max(1, int(w*scale)), max(1, int(h*scale))
        x, y = (cw-dw)//2, (ch-dh)//2
        self.rect = (x, y, dw, dh)
        if not self._items:
            self._items.update(self.create_items(x, y, cw))
        items = self._items
        if frame is not self._render_frame or (dw, dh) != self._render_size:
            self.draw_video(frame, dw, dh)
        self.canvas_coords(items['video'], x, y)
        a, b, c, d = self.roi
        self.canvas_coords(items['roi'], x+a*dw, y+b*dh, x+c*dw, y+d*dh)
        self.canvas_coords(items['bar'], 0, 0, cw, STATUS_BAR_HEIGHT)
        self.canvas_configure(items['status'], text=self.overlay, width=max(100, cw-28))
        for key in ('polygon', 'label', 'label_bg'):
            self.canvas_configure(items[key], state='normal' if row is not None else 'hidden')
        body_box = row.get('body_box') if row is not None else None
        self.canvas_configure(items['body'], state='normal' if body_box is not None else 'hidden')
        if body_box is not None:
            self.canvas.coords(items['body'], *to_canvas(body_box, x, y, dw, dh, w, h))
        if row is not None:
            self.draw_marking(row, x, y, dw, dh, w, h)
        detections = self.visible_detections(frame)
        if detections or self._detections_drawn:
            self.draw_detections(detections, x, y, dw, dh, w, h)
            self._detections_drawn = bool(detections)
        chips = self.visible_chips(frame)
        if chips or self._chips_drawn:
            self.draw_chips(chips, x, y, dw, dh, w, h)
            self._chips_drawn = bool(chips)
        self.performance['rendering_ms'] = (time.perf_counter()-started)*1000

    def draw_video(self, frame, dw, dh):
        """Show a new frame (or the same frame at a new size)."""
        now = time.monotonic()
        rate_start, count = self._preview_rate or (now, 0)
        count += 1
        if now-rate_start >= 1.:
            self.performance['preview_fps'] = count/(now-rate_start)
            rate_start, count = now, 0
        self._preview_rate = (rate_start, count)
        preview = Image.fromarray(cv2.cvtColor(preview_resize(frame, (dw, dh)), cv2.COLOR_BGR2RGB))
        if self.photo is not None and self._photo_size == (dw, dh):
            # Reuse the Tk image: paste is cheaper than creating a new one each frame.
            self.photo.paste(preview)
        else:
            self.photo = ImageTk.PhotoImage(preview)
            self._photo_size = (dw, dh)
            self.canvas.itemconfigure(self._items['video'], image=self.photo)
        self._render_frame, self._render_size = frame, (dw, dh)

    def draw_marking(self, row, x, y, dw, dh, w, h):
        """Tracked marking outline and its label (text + description)."""
        items = self._items
        label, colour = overlay_label(row, self.catalog is not None)
        points = to_canvas(row['box'], x, y, dw, dh, w, h)
        self.canvas.coords(items['polygon'], *points)
        self.canvas.itemconfigure(items['polygon'], outline=colour)
        width = min(330, max(120, dw-24))
        lx = max(x+8, min(min(points[0::2]), x+dw-width-8))
        ly = max(LABEL_TOP, min(points[1::2])-58)
        self.canvas.coords(items['label'], lx, ly)
        self.canvas.itemconfigure(items['label'], text=label, fill=colour, width=width)
        bounds = self.canvas.bbox(items['label'])
        if bounds:
            if bounds[3] > y+dh-6:
                self.canvas.move(items['label'], 0, y+dh-6-bounds[3])
                bounds = self.canvas.bbox(items['label'])
            self.canvas.coords(items['label_bg'], bounds[0]-5, bounds[1]-4, bounds[2]+5, bounds[3]+4)
            self.canvas.itemconfigure(items['label_bg'], outline=colour)

    def draw_detections(self, detections, x, y, dw, dh, w, h):
        """Detector outlines reuse pooled canvas items (0.8.3.2)."""
        if self._detection_items is None:
            self._detection_items = ItemPool(self.canvas, 'detection')
        pool = self._detection_items
        pool.begin()
        for found in detections:
            x1, y1, x2, y2 = found['box']
            if found.get('polygon'):
                pool.item('polygon', to_canvas(found['polygon'], x, y, dw, dh, w, h),
                          outline=DETECTION_COLOUR, width=2, dash=(6, 3), fill='')
            else:
                pool.item('rectangle', [x+x1*dw/w, y+y1*dh/h, x+x2*dw/w, y+y2*dh/h],
                          outline=DETECTION_COLOUR, width=2, dash=(6, 3))
            pool.item('text', [x+x1*dw/w+3, y+y1*dh/h+2], anchor='nw', fill=DETECTION_COLOUR,
                      text=f"IC {found['score']:.2f}", font=('Segoe UI', 9, 'bold'))
        pool.finish()

    def draw_chips(self, placed, x, y, dw, dh, w, h):
        """Multi-chip overlay: body outline, marking outline and a numbered label
        per chip. Pooled canvas items as in draw_detections."""
        if self._chip_items is None:
            self._chip_items = ItemPool(self.canvas, 'multi_chip', raise_items=True)
        pool = self._chip_items
        pool.begin()
        database_loaded = self.catalog is not None
        # Markings are obstacles too: a label should not hide another chip's text.
        occupied = []
        for entry in placed:
            if entry['box'] is not None:
                points = to_canvas(entry['box'], x, y, dw, dh, w, h)
                occupied.append((min(points[0::2]), min(points[1::2]), max(points[0::2]), max(points[1::2])))
        for entry in placed:
            chip = entry['chip']
            label, colour = multi_chip.describe(chip, database_loaded)
            if entry['body'] is not None:
                pool.item('polygon', to_canvas(entry['body'], x, y, dw, dh, w, h),
                          outline=BODY_COLOUR, width=2, dash=(5, 3), fill='')
            anchor = entry['box'] if entry['box'] is not None else entry['body']
            if entry['box'] is not None:
                pool.item('polygon', to_canvas(entry['box'], x, y, dw, dh, w, h), outline=colour, width=2, fill='')
            if anchor is None:
                x0, y0, x1, y1 = chip['region']
                anchor = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
            points = to_canvas(anchor, x, y, dw, dh, w, h)
            width = min(240, max(110, dw-24))
            lx = max(x+6, min(min(points[0::2]), x+dw-width-6))
            top, bottom = min(points[1::2]), max(points[1::2])
            background = pool.item('rectangle', [lx, top, lx+1, top+1], fill=BACKGROUND, outline=colour)
            text = pool.item('text', [lx, top], anchor='nw', text=label, fill=colour, width=width,
                             font=('Segoe UI', 10, 'bold'))
            bounds = self.canvas.bbox(text)
            if bounds:
                tw, th = bounds[2]-bounds[0], bounds[3]-bounds[1]
                ly = free_label_row(lx, tw, th, top, bottom, LABEL_TOP, max(LABEL_TOP, y+dh-th-4), occupied)
                self.canvas.move(text, 0, ly-bounds[1])
                occupied.append((lx-4, ly-3, lx+tw+4, ly+th+3))
                self.canvas.coords(background, *occupied[-1])
                self.canvas.tag_raise(text)
        pool.finish()


def free_label_row(lx, tw, th, top, bottom, low, high, occupied):
    """Label top: above the marking, else below it, else the nearest free place
    going down; labels must not cover each other or other markings."""
    options = [top-th-8, bottom+8] + [top-th-8+k*(th+8) for k in range(1, 12)]
    for ly in options:
        ly = min(max(ly, low), high)
        box = (lx-4, ly-3, lx+tw+4, ly+th+3)
        if not any(box[0] < o[2] and o[0] < box[2] and box[1] < o[3] and o[1] < box[3] for o in occupied):
            return ly
    return min(max(top-th-8, low), high)
