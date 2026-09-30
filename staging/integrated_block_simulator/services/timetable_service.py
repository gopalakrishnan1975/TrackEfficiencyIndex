import pandas as pd

def synthetic_timetable() -> pd.DataFrame:
    rows=[]
    for i in range(40):
        enter=300+i*25
        rows.append({"train_id":f"P{i+1:03d}","train_class":"Coaching","section":"A-B","direction":"UP" if i%2==0 else "DOWN","enter_min":enter%1440,"exit_min":(enter+30)%1440,"max_speed_kph":130,"weight":1.0,"synthetic":True})
    for i in range(30):
        enter=330+i*35
        rows.append({"train_id":f"G{i+1:03d}","train_class":"Goods","section":"A-B","direction":"UP" if i%2==0 else "DOWN","enter_min":enter%1440,"exit_min":(enter+55)%1440,"max_speed_kph":60,"weight":0.35,"synthetic":True})
    return pd.DataFrame(rows)

def validate_timetable(df: pd.DataFrame) -> pd.DataFrame:
    required={"train_id","train_class","section","direction","enter_min","exit_min","max_speed_kph"}
    missing=required-set(df.columns)
    if missing:
        raise ValueError(f"Timetable is missing columns: {sorted(missing)}")
    out=df.copy()
    if "weight" not in out: out["weight"]=1.0
    if "synthetic" not in out: out["synthetic"]=False
    return out
