import pandas as pd

def synthetic_timetable(passenger_count:int=40, goods_count:int=30,
                        passenger_speed_kph:float=110.0, goods_speed_kph:float=60.0) -> pd.DataFrame:
    """Synthetic placeholder timetable for UI experiments."""
    rows=[]
    pcount=max(0,int(passenger_count)); gcount=max(0,int(goods_count))
    pstep=max(1, int(1080/max(1,pcount)))
    gstep=max(1, int(1080/max(1,gcount)))
    for i in range(pcount):
        enter=(240+i*pstep)%1440
        rows.append({"train_id":f"P{i+1:03d}","train_class":"Coaching","section":"A-B",
                     "direction":"UP" if i%2==0 else "DOWN","enter_min":enter,
                     "exit_min":(enter+30)%1440,"max_speed_kph":float(passenger_speed_kph),
                     "weight":1.0,"synthetic":True})
    for i in range(gcount):
        enter=(300+i*gstep)%1440
        rows.append({"train_id":f"G{i+1:03d}","train_class":"Goods","section":"A-B",
                     "direction":"UP" if i%2==0 else "DOWN","enter_min":enter,
                     "exit_min":(enter+55)%1440,"max_speed_kph":float(goods_speed_kph),
                     "weight":0.35,"synthetic":True})
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
