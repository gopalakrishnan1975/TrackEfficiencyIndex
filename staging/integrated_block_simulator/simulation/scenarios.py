from models.domain import WorkSite, MachinePool, PlannerPolicy

WORK_TYPES={
 "BCM-Plain Track":{"productivity":0.40,"block":180,"machines":{"BCM":1,"DUOMATIC":1,"DGS":1}},
 "BCM-Point Machine":{"productivity":0.10,"block":240,"machines":{"BCM":1}},
 "CTR/Primary-PQRS":{"productivity":0.45,"block":240,"machines":{"PQRS":1,"DUOMATIC":1}},
 "CTR/Primary-TRT":{"productivity":0.60,"block":240,"machines":{"TRT":1,"DUOMATIC":1}},
 "TRR":{"productivity":0.75,"block":180,"machines":{"TRR":1}},
 "Through Tamping":{"productivity":1.50,"block":150,"machines":{"DUOMATIC":1}},
 "Crossovers":{"productivity":0.10,"block":240,"machines":{"XOVER_GANG":1}},
 "Rail Panel Unloading":{"productivity":1.0,"block":120,"machines":{"MATERIAL_TRAIN":1}},
 "Ballast Unloading":{"productivity":1.2,"block":120,"machines":{"BALLAST_RAKE":1}},
 "Sleeper Unloading":{"productivity":1.0,"block":120,"machines":{"MATERIAL_TRAIN":1}},
 "UTV":{"productivity":5.0,"block":90,"machines":{"UTV":1}},
}

def default_works():
    return [
      WorkSite("W1","BCM-Plain Track","A-B","UP",10,14,1,0,25,130,0.40,180,True,{"BCM":1,"DUOMATIC":1,"DGS":1},synthetic=True),
      WorkSite("W2","TRR","A-B","UP",20,24,2,0,35,130,0.75,180,True,{"TRR":1},synthetic=True),
    ]

def default_machines():
    return MachinePool({"BCM":2,"DUOMATIC":1,"DGS":1,"TRR":1,"PQRS":1,"TRT":1,"XOVER_GANG":1,"MATERIAL_TRAIN":1,"BALLAST_RAKE":1,"UTV":1})

def default_policy():
    return PlannerPolicy(max_weighted_ea_min_per_day=250,min_goods_paths_per_day=20,max_block_minutes_per_day=360,allow_shadow_parallelism=True)
