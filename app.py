from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash, jsonify
import os
import datetime
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-change-me")

# --------------------------
# Helpers
# --------------------------
def signed_to_abs_from_own(s):
    """
    Convert signed yard line to absolute distance from own goal line (0..100).
    - Negative => own X (e.g., -20 -> 20)
    - Positive => opponent X (e.g., +30 -> 70)
    """
    if s is None or s == "":
        return None
    s = str(s).strip()
    try:
        # normalize unicode minus and remove plus
        v = int(s.replace("+", "").replace("−", "-"))
    except Exception:
        return None
    if s.startswith("-"):
        return max(0, min(100, v))
    else:
        return max(0, min(100, 100 - v))

def distance_from_to(a, b):
    aa, bb = signed_to_abs_from_own(a), signed_to_abs_from_own(b)
    if aa is None or bb is None:
        return ""
    return abs(bb - aa)

def compute_fg_distance(yl):
    """Field goal distance = |YL| + 18 (10 EZ + 8 snap)."""
    try:
        n = int(str(yl).replace("+", "").replace("-", ""))
        return str(abs(n) + 18)
    except Exception:
        return ""

def compute_ko_distance(yl, res_yl):
    return distance_from_to(yl, res_yl)

def compute_punt_distance(kick_yl, landed_yl):
    return distance_from_to(kick_yl, landed_yl)

def ensure_ids(data_list):
    """
    Ensure each kick dict has a numeric 'id'. Maintains a running counter in session.
    """
    next_id = session.get("next_kick_id", 1)
    changed = False
    for row in data_list:
        if "id" not in row:
            row["id"] = next_id
            next_id += 1
            changed = True
    if changed:
        session["next_kick_id"] = next_id
        session["data"] = data_list

def update_last_used_from_row(row):
    """
    Store 'last used' defaults in session (excluding stopwatch values).
    These can be fetched by the UI to prefill forms.
    """
    last = session.get("last_used", {})

    # Common
    if "Kicker" in row and row["Kicker"]:
        last["kicker"] = row["Kicker"]
    if "Holder" in row and row["Holder"]:
        last["holder"] = row["Holder"]
    if "Longsnapper" in row and row["Longsnapper"]:
        last["longsnapper"] = row["Longsnapper"]

    ktype = row.get("Kick Type", "")
    if ktype == "Field Goal":
        if row.get("Field Goal_Yard Line"): last["fg_yard_line"] = row["Field Goal_Yard Line"]
        if row.get("Field Goal_Position"):  last["fg_hash"]      = row["Field Goal_Position"]
        # Intentionally do NOT store stopwatch (op time) as last used
        if row.get("Field Goal_Result"):    last["fg_result"]   = row["Field Goal_Result"]
    elif ktype == "Kickoff":
        if row.get("Kickoff_Yard Line"):        last["ko_yard_line"]       = row["Kickoff_Yard Line"]
        if row.get("Kickoff_Position"):         last["ko_hash"]            = row["Kickoff_Position"]
        if row.get("Kickoff_Result Yard Line"): last["ko_result_yard_line"]= row["Kickoff_Result Yard Line"]
        if row.get("Kickoff_Landing Location"): last["ko_location"]        = row["Kickoff_Landing Location"]
        # Exclude 'Kickoff_Hang Time' from defaults
    elif ktype == "Punt":
        if row.get("Punt_Kick Yard Line"):   last["punt_kick_yl"]   = row["Punt_Kick Yard Line"]
        if row.get("Punt_Kick Location"):    last["punt_kick_loc"]  = row["Punt_Kick Location"]
        if row.get("Punt_Landed Yard Line"): last["punt_landed_yl"] = row["Punt_Landed Yard Line"]
        if row.get("Punt_Landing Location"): last["punt_landed_loc"]= row["Punt_Landing Location"]
        # Exclude Snap / H2F / Hang from defaults

    session["last_used"] = last

# --------------------------
# Health (Render / pingers)
# --------------------------
@app.route("/healthz")
def healthz():
    return "ok", 200

# --------------------------
# Session start (iPad date)
# --------------------------
@app.route('/start_session', methods=['POST'])
def start_session():
    client_date = request.form.get('client_date')
    if client_date:
        session['workout_date'] = client_date
    else:
        session['workout_date'] = datetime.date.today().isoformat()
    session['data'] = []              # reset entries
    session['next_kick_id'] = 1       # reset id counter
    flash('New session started.')
    return redirect(url_for('index'))

# --------------------------
# Main page + save kick
# --------------------------
@app.route("/", methods=["GET","POST"])
def index():
    if "workout_date" not in session:
        # First load: default to client date if passed (rare on GET), else server date
        session["workout_date"] = request.form.get("client_date") or datetime.date.today().isoformat()
        session["data"] = []
        session["next_kick_id"] = 1

    if request.method == "POST" and request.form.get("action") == "save_kick":
        ktype = request.form.get("kick_type")

        # Common fields
        row = {
            "Kick Type": ktype,
            "Kicker": request.form.get("kicker",""),
            "Longsnapper": request.form.get("longsnapper",""),
            "Holder": request.form.get("holder",""),
        }

        # Type-specific capture + distance compute
        if ktype == "Field Goal":
            yl = request.form.get("fg_yard_line","")
            row.update({
                "Field Goal_Yard Line": yl,
                "Field Goal_Position": request.form.get("fg_hash",""),
                "Field Goal_Op Time": request.form.get("fg_op_time",""),    # stopwatch (not defaulted)
                "Field Goal_Result": request.form.get("fg_result",""),
                "Field Goal_Distance": compute_fg_distance(yl) if yl not in ("","-","+") else ""
            })

        elif ktype == "Kickoff":
            yl = request.form.get("ko_yard_line","")
            res_yl = request.form.get("ko_result_yard_line","")
            row.update({
                "Kickoff_Yard Line": yl,
                "Kickoff_Position": request.form.get("ko_hash",""),
                "Kickoff_Result Yard Line": res_yl,
                "Kickoff_Landing Location": request.form.get("ko_location",""),
                "Kickoff_Hang Time": request.form.get("ko_hang_time",""),    # stopwatch (not defaulted)
                "Kickoff_Distance": compute_ko_distance(yl, res_yl)
            })

        elif ktype == "Punt":
            kick_yl = request.form.get("punt_kick_yl","")
            landed_yl = request.form.get("punt_landed_yl","")
            row.update({
                "Punt_Kick Yard Line": kick_yl,
                "Punt_Kick Location": request.form.get("punt_kick_loc",""),
                "Punt_Landed Yard Line": landed_yl,
                "Punt_Landing Location": request.form.get("punt_landed_loc",""),
                "Punt_Snap Time": request.form.get("punt_snap_time",""),        # stopwatch (not defaulted)
                "Punt_Hand to Foot": request.form.get("punt_hand_to_foot",""),  # stopwatch (not defaulted)
                "Punt_Hang Time": request.form.get("punt_hang_time",""),        # stopwatch (not defaulted)
                "Punt_Distance": compute_punt_distance(kick_yl, landed_yl)
            })

        # Assign a stable ID
        next_id = session.get("next_kick_id", 1)
        row["id"] = next_id
        session["next_kick_id"] = next_id + 1

        # Append to session list
        data = session.get("data", [])
        data.append(row)
        session["data"] = data

        # Update "last used" defaults (excluding stopwatch fields)
        update_last_used_from_row(row)

        flash("Kick saved.")
        return redirect(url_for("index"))

    return render_template("index.html")

# --------------------------
# APIs for side drawer & defaults
# --------------------------
@app.route('/kicks', methods=['GET'])
def kicks_list():
    """
    Returns all kicks in the current session, ensuring each has an 'id'.
    """
    data = session.get("data", [])
    ensure_ids(data)
    return jsonify(data)

@app.route('/kick/<int:kid>', methods=['GET', 'POST'])
def kick_detail(kid):
    """
    GET: returns a single kick dict.
    POST: updates fields; recomputes distances as needed.
    """
    data = session.get("data", [])
    ensure_ids(data)
    k = next((r for r in data if r.get("id") == kid), None)
    if not k:
        return jsonify({"error": "not found"}), 404

    if request.method == 'GET':
        return jsonify(k)

    # Accept JSON or form
    incoming = request.get_json(silent=True) or request.form

    # Update known fields if provided
    fields = [
        'Kick Type','Kicker','Holder','Longsnapper',
        'Field Goal_Yard Line','Field Goal_Position','Field Goal_Result','Field Goal_Op Time',
        'Kickoff_Yard Line','Kickoff_Position','Kickoff_Result Yard Line','Kickoff_Landing Location','Kickoff_Hang Time',
        'Punt_Kick Yard Line','Punt_Kick Location','Punt_Landed Yard Line','Punt_Landing Location',
        'Punt_Snap Time','Punt_Hand to Foot','Punt_Hang Time'
    ]
    for f in fields:
        if f in incoming:
            k[f] = incoming.get(f)

    # Recompute distances based on type/inputs
    ktype = k.get("Kick Type", "")
    if ktype == "Field Goal":
        yl = k.get("Field Goal_Yard Line", "")
        k["Field Goal_Distance"] = compute_fg_distance(yl) if yl not in ("","-","+") else ""
    elif ktype == "Kickoff":
        yl = k.get("Kickoff_Yard Line", "")
        res_yl = k.get("Kickoff_Result Yard Line", "")
        k["Kickoff_Distance"] = compute_ko_distance(yl, res_yl)
    elif ktype == "Punt":
        kyl = k.get("Punt_Kick Yard Line", "")
        lyl = k.get("Punt_Landed Yard Line", "")
        k["Punt_Distance"] = compute_punt_distance(kyl, lyl)

    # Write back to session
    for i, row in enumerate(data):
        if row.get("id") == kid:
            data[i] = k
            break
    session["data"] = data

    # Update last-used defaults (excluding stopwatch)
    update_last_used_from_row(k)

    return jsonify({"ok": True, "kick": k})

@app.route('/last_used', methods=['GET'])
def last_used():
    """Return last used defaults so the UI can prefill fields."""
    return jsonify(session.get("last_used", {}))

# --------------------------
# PDF Export
# --------------------------
@app.route("/end_session")
def end_session():
    data = session.get("data", [])
    if not data:
        flash("No data to export.")
        return redirect(url_for("index"))

    # Split by type
    fgs = [r for r in data if r.get("Kick Type") == "Field Goal"]
    kos = [r for r in data if r.get("Kick Type") == "Kickoff"]
    punts = [r for r in data if r.get("Kick Type") == "Punt"]

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elems = []

    # Header
    logo_path = os.path.join("static","img","harvard_shield.png")
    try:
        elems.append(Image(logo_path, width=0.7*inch, height=0.7*inch))
    except Exception:
        pass
    elems.append(Paragraph(f"Practice Results — {session.get('workout_date','')}", styles["Title"]))
    elems.append(Spacer(1, 14))

    def styled_table(data, widths=None):
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.Color(0.79,0,0.09)), # crimson
            ("TEXTCOLOR", (0,0), (-1,0), colors.whitesmoke),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("ALIGN", (0,0), (-1,0), "CENTER"),
            ("FONTSIZE", (0,0), (-1,0), 10),
            ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#333333")),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#111111"), colors.HexColor("#1a1a1a")]),
            ("TEXTCOLOR", (0,1), (-1,-1), colors.whitesmoke),
            ("FONTSIZE", (0,1), (-1,-1), 9),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ]))
        return t

    if fgs:
        elems.append(Paragraph("Field Goal", styles["Heading2"]))
        head = ["Kick #","Kicker","Holder","Snapper","Yard Line","Hash","Distance","Result","Op Time"]
        rows = []
        for i, r in enumerate(fgs, 1):
            yl = r.get("Field Goal_Yard Line","")
            dist = r.get("Field Goal_Distance","") or compute_fg_distance(yl)
            rows.append([
                i, r.get("Kicker",""), r.get("Holder",""), r.get("Longsnapper",""),
                yl, r.get("Field Goal_Position",""), dist, r.get("Field Goal_Result",""),
                r.get("Field Goal_Op Time","")
            ])
        elems.extend([styled_table([head]+rows), Spacer(1, 16)])

    if punts:
        elems.append(Paragraph("Punt", styles["Heading2"]))
        head = ["Kick #","Kicker","Snapper","Yard Line","Hash","Distance","Location","Snap","Hand-to-foot","Hang"]
        rows = []
        for i, r in enumerate(punts, 1):
            dist = r.get("Punt_Distance","") or compute_punt_distance(r.get("Punt_Kick Yard Line",""), r.get("Punt_Landed Yard Line",""))
            rows.append([
                i, r.get("Kicker",""), r.get("Longsnapper",""), r.get("Punt_Kick Yard Line",""),
                r.get("Punt_Kick Location",""), dist, r.get("Punt_Landing Location",""),
                r.get("Punt_Snap Time",""), r.get("Punt_Hand to Foot",""), r.get("Punt_Hang Time","")
            ])
        elems.extend([styled_table([head]+rows), Spacer(1, 16)])

    if kos:
        elems.append(Paragraph("Kickoff", styles["Heading2"]))
        head = ["Kick #","Kicker","Yard Line","Hash","Distance","Hang","Location"]
        rows = []
        for i, r in enumerate(kos, 1):
            dist = r.get("Kickoff_Distance","") or compute_ko_distance(r.get("Kickoff_Yard Line",""), r.get("Kickoff_Result Yard Line",""))
            rows.append([
                i, r.get("Kicker",""), r.get("Kickoff_Yard Line",""),
                r.get("Kickoff_Position",""), dist,
                r.get("Kickoff_Hang Time",""), r.get("Kickoff_Landing Location","")
            ])
        elems.extend([styled_table([head]+rows), Spacer(1, 16)])

    doc.build(elems)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="practice_results.pdf", mimetype="application/pdf")

# --------------------------
# Entry point
# --------------------------
if __name__ == "__main__":
    app.run(debug=True)
