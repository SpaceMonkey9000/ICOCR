"""Bounded sidebar status; full recognition evidence belongs in Diagnostics."""

def candidate_status(row):
    match = row.get('selected_database_match')
    accepted = match and not row.get('provisional') and not row.get('rejection_reason')
    if accepted:
        kind = {'abbreviated': 'Abbreviated match', 'family_suffix': 'Suffix match',
                'partial': 'Partial match'}.get(match.get('match_type'), 'Database match')
        lines = [kind + ' (unverified)', match['part'],
                 match.get('entry_function') or match.get('component_function') or match.get('description') or row.get('function_summary') or 'Function not recorded']
    else:
        lines = ['No confirmed identity', row.get('text') or row.get('key', ''),
                 'Database suggestions only' if row.get('database_matches') else 'No database match']
    if row.get('provisional') or row.get('rejection_reason'):
        lines.append('Warning: reading unconfirmed')
    if row.get('conflicts'):
        lines.append('Warning: conflicting markings')
    if row.get('database_ambiguous'):
        lines.append('Warning: ambiguous database variants')
    if accepted and match.get('match_type') in ('abbreviated', 'family_suffix'):
        lines.append('Manufacturer/package unresolved')
    if row.get('ocr_correction'):
        lines.append('OCR correction applied')
    return '\n'.join(' '.join(str(line).split()) for line in lines)


def fit_line(text, width, measure):
    """Ellipsize using actual font metrics, including long unbroken part codes."""
    text = ' '.join(text.split())
    if measure(text) <= width:
        return text
    if measure('…') > width:
        return ''
    # 0.8.4.3: binary search on the kept length (font measuring is a Tk call;
    # trimming one character at a time took hundreds of calls for long text).
    # Widths grow with length, so this keeps the longest prefix that fits.
    low, high = 0, len(text) - 1      # text[:low] + '…' fits; the full text does not
    while low < high:
        middle = (low + high + 1) // 2
        if measure(text[:middle] + '…') <= width:
            low = middle
        else:
            high = middle - 1
    return text[:low] + '…'


class StatusPanel:
    LINES = 8

    def __init__(self, parent, variable, lines=None):
        from tkinter import ttk, font
        self.LINES = self.LINES if lines is None else lines
        self.variable = variable
        self.font = font.nametofont('TkDefaultFont')
        self.frame = ttk.Frame(parent, height=self.font.metrics('linespace') * self.LINES + 8)
        self.frame.pack_propagate(False)
        self.label = ttk.Label(self.frame, anchor='nw', justify='left', font=self.font)
        self.label.pack(fill='both', expand=True, pady=4)
        self.frame.bind('<Configure>', self.render)
        self.trace = variable.trace_add('write', self.render)
        self.frame.bind('<Destroy>', self.destroy, add='+')
        self.render()

    def render(self, *args):
        width = max(0, self.frame.winfo_width() - 4)
        lines = self.variable.get().splitlines()
        if len(lines) > self.LINES:
            lines = lines[:self.LINES]
            lines[-1] += '…'
        self.label.configure(text='\n'.join(fit_line(line, width, self.font.measure) for line in lines))

    def destroy(self, event):
        if event.widget == self.frame:
            self.variable.trace_remove('write', self.trace)
