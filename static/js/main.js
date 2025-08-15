
// Single-phase stopwatch
class SingleStopwatch {
  constructor(displayId, fieldId) {
    this.display = document.getElementById(displayId);
    this.field = document.getElementById(fieldId);
    this.t0 = 0; this.dt = 0; this.running = false; this.raf = null;
    if (this.display) this.display.textContent = "0.000 s";
  }
  start(){ if (this.running) return; this.running = true; this.t0 = performance.now(); const tick=()=>{ if(!this.running) return; this.dt=(performance.now()-this.t0)/1000; this.display.textContent=this.dt.toFixed(3)+" s"; this.raf=requestAnimationFrame(tick);}; this.raf=requestAnimationFrame(tick); }
  stop(){ if(!this.running) return; this.running=false; cancelAnimationFrame(this.raf); if(this.field) this.field.value=this.dt.toFixed(3); }
  reset(){ this.running=false; cancelAnimationFrame(this.raf); this.dt=0; if(this.display) this.display.textContent="0.000 s"; if(this.field) this.field.value=""; }
}

// Punt 3-phase
class PuntStopwatch {
  constructor(displayId, snapId, h2fId, hangId){
    this.display = document.getElementById(displayId);
    this.snapF = document.getElementById(snapId);
    this.h2fF = document.getElementById(h2fId);
    this.hangF = document.getElementById(hangId);
    this.phase = "idle"; this.t0=0;
    this.snap=0; this.h2f=0; this.hang=0;
    this._update();
  }
  start(){ if(this.phase!=="idle") return; this.phase="snap"; this.t0=performance.now(); this._tick(); }
  breakPhase(){ if(this.phase==="snap"){ this.snap=(performance.now()-this.t0)/1000; this.phase="h2f"; this.t0=performance.now(); this._update(); } else if(this.phase==="h2f"){ this.h2f=(performance.now()-this.t0)/1000; this.phase="hang"; this.t0=performance.now(); this._update(); } }
  stop(){ if(this.phase==="hang"){ this.hang=(performance.now()-this.t0)/1000; } this.phase="idle"; this._update(); this.snapF.value=this.snap.toFixed(3); this.h2fF.value=this.h2f.toFixed(3); this.hangF.value=this.hang.toFixed(3); cancelAnimationFrame(this.raf); }
  reset(){ this.phase="idle"; this.snap=this.h2f=this.hang=0; this._update(); cancelAnimationFrame(this.raf); this.snapF.value=this.h2fF.value=this.hangF.value=""; }
  _tick(){ if(this.phase==="idle") return; this._update(); this.raf=requestAnimationFrame(()=>this._tick()); }
  _update(){ const s=this.snap.toFixed(3), h=this.h2f.toFixed(3), g=this.hang.toFixed(3); const p=this.phase.toUpperCase(); this.display.textContent = `Snap ${s} | H2F ${h} | Hang ${g} ${this.phase!=="idle" ? "(" + p + ")" : ""}`; }
}

// Global instances
window.sw = {
  fg: new SingleStopwatch("fg_timer", "fg_op_time"),
  ko: new SingleStopwatch("ko_timer", "ko_hang_time"),
  punt: new PuntStopwatch("punt_timer","punt_snap_time","punt_hand_to_foot","punt_hang_time"),
};

// Keypad logic
window.keypad = {
  target: null,
  open(id){ this.target = document.getElementById(id); document.getElementById("keypadInput").value = this.target.value || ""; $("#keypadModal").modal("show"); },
  press(k){ const input = document.getElementById("keypadInput"); input.value += k; },
  toggleSign(){ const input=document.getElementById("keypadInput"); if(!input.value){ input.value = "-"; return; } if(input.value.startsWith("-")) input.value = input.value.slice(1); else input.value = "-" + input.value; },
  clear(){ document.getElementById("keypadInput").value=""; },
  apply(){ if(this.target) this.target.value = document.getElementById("keypadInput").value; $("#keypadModal").modal("hide"); }
};
window.openKeypad = (id)=> keypad.open(id);
