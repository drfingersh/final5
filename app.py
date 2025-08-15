
from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
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

# --- Helpers ---
def signed_to_abs_from_own(s):
    if s is None or s == "":
        return None
    s = str(s).strip()
    try:
        v = int(s.replace("+","").replace("−","-"))
    except Exception:
        return None
    if s.startswith("-"):
        # own v
        return max(0, min(100, v))
    else:
        # opponent v
        return max(0, min(100, 100 - v))

def distance_from_to(a, b):
    aa, bb = signed_to_abs_from_own(a), signed_to_abs_from_own(b)
    if aa is None or bb is None:
        return ""
    return abs(bb - aa)

# --- Routes ---
@app.route("/", methods=["GET","POST"])
def index():
    if "workout_date" not in session:
        # default to client date if passed, else server date
        session["workout_date"] = request.form.get("client_date") or datetime.date.today().isoformat()
        session["data"] = []

    if request.method == "POST" and request.form.get("action") == "save_kick":
        ktype = request.form.get("kick_type")
        # Common
        row = {
            "Kick Type": ktype,
            "Kicker": request.form.get("kicker",""),
            "Longsnapper": request.form.get("longsnapper",""),
            "Holder": request.form.get("holder",""),
        }
        if ktype == "Field Goal":
            yl = request.form.get("fg_yard_line","")
            row.update({
                "Field Goal_Yard Line": yl,
                "Field Goal_Position": request.form.get("fg_hash",""),
                "Field Goal_Op Time": request.form.get("fg_op_time",""),
                "Field Goal_Result": request.form.get("fg_result",""),
                "Field Goal_Distance": str(int(abs(int(str(yl).replace('+','').replace('-','') or 0))) + 18) if yl not in ("","-","+") else ""
            })
        elif ktype == "Kickoff":
            yl = request.form.get("ko_yard_line","")
            res_yl = request.form.get("ko_result_yard_line","")
            row.update({
                "Kickoff_Yard Line": yl,
                "Kickoff_Position": request.form.get("ko_hash",""),
                "Kickoff_Result Yard Line": res_yl,
                "Kickoff_Landing Location": request.form.get("ko_location",""),
                "Kickoff_Hang Time": request.form.get("ko_hang_time",""),
                "Kickoff_Distance": distance_from_to(yl, res_yl)
            })
        elif ktype == "Punt":
            kick_yl = request.form.get("punt_kick_yl","")
            landed_yl = request.form.get("punt_landed_yl","")
            row.update({
                "Punt_Kick Yard Line": kick_yl,
                "Punt_Kick Location": request.form.get("punt_kick_loc",""),
                "Punt_Landed Yard Line": landed_yl,
                "Punt_Landing Location": request.form.get("punt_landed_loc",""),
                "Punt_Snap Time": request.form.get("punt_snap_time",""),
                "Punt_Hand to Foot": request.form.get("punt_hand_to_foot",""),
                "Punt_Hang Time": request.form.get("punt_hang_time",""),
                "Punt_Distance": distance_from_to(kick_yl, landed_yl)
            })
        data = session.get("data", [])
        data.append(row)
        session["data"] = data
        flash("Kick saved.")
        return redirect(url_for("index"))

    return render_template("index.html")

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
            if r.get("Field Goal_Distance","") == "":
                try:
                    dist = str(int(abs(int(str(yl).replace('+','').replace('-','') or 0))) + 18)
                except Exception:
                    dist = ""
            else:
                dist = r.get("Field Goal_Distance","")
            rows.append([i, r.get("Kicker",""), r.get("Holder",""), r.get("Longsnapper",""),
                         yl, r.get("Field Goal_Position",""), dist, r.get("Field Goal_Result",""),
                         r.get("Field Goal_Op Time","")])
        elems.extend([styled_table([head]+rows), Spacer(1, 16)])

    if punts:
        elems.append(Paragraph("Punt", styles["Heading2"]))
        head = ["Kick #","Kicker","Snapper","Yard Line","Hash","Distance","Location","Snap","Hand-to-foot","Hang"]
        rows = []
        for i, r in enumerate(punts, 1):
            dist = r.get("Punt_Distance","")
            rows.append([i, r.get("Kicker",""), r.get("Longsnapper",""), r.get("Punt_Kick Yard Line",""),
                         r.get("Punt_Kick Location",""), dist, r.get("Punt_Landing Location",""),
                         r.get("Punt_Snap Time",""), r.get("Punt_Hand to Foot",""), r.get("Punt_Hang Time","")])
        elems.extend([styled_table([head]+rows), Spacer(1, 16)])

    if kos:
        elems.append(Paragraph("Kickoff", styles["Heading2"]))
        head = ["Kick #","Kicker","Yard Line","Hash","Distance","Hang","Location"]
        rows = []
        for i, r in enumerate(kos, 1):
            rows.append([i, r.get("Kicker",""), r.get("Kickoff_Yard Line",""),
                         r.get("Kickoff_Position",""), r.get("Kickoff_Distance",""),
                         r.get("Kickoff_Hang Time",""), r.get("Kickoff_Landing Location","")])
        elems.extend([styled_table([head]+rows), Spacer(1, 16)])

    doc.build(elems)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="practice_results.pdf", mimetype="application/pdf")

if __name__ == "__main__":
    app.run(debug=True)
