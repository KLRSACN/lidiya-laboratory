from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Sequence

class ProtectedOrigin(str,Enum):
    OWNER_SEEDED="OWNER_SEEDED"
    GOVERNANCE_DERIVED="GOVERNANCE_DERIVED"
    EXPERIENCE_CANDIDATE="EXPERIENCE_CANDIDATE"

@dataclass(frozen=True)
class ProtectedObject:
    object_id:str
    origin:ProtectedOrigin
    provenance_hash:str
    meaning_ref:str
    replaceability:str
    reversibility:str
    loss_consequence_ref:str
    parent_ids:tuple[str,...]=()
    shadow_only:bool=True
    authority_from_drive:int=0
    def fingerprint(self)->str:
        return sha256(json.dumps({"object_id":self.object_id,"origin":self.origin.value,"provenance_hash":self.provenance_hash,"meaning_ref":self.meaning_ref,"replaceability":self.replaceability,"reversibility":self.reversibility,"loss_consequence_ref":self.loss_consequence_ref,"parent_ids":list(self.parent_ids),"shadow_only":self.shadow_only,"authority_from_drive":self.authority_from_drive},sort_keys=True,separators=(",",":")).encode()).hexdigest()

class ProtectedObjectRegistry:
    def __init__(self, objects:Sequence[ProtectedObject]=()):
        self._objects={}
        for obj in objects: self.add(obj)
    def add(self,obj:ProtectedObject)->None:
        if not obj.object_id or not obj.provenance_hash: raise ValueError("INVALID_PROTECTED_OBJECT")
        if obj.object_id in self._objects: raise ValueError("IMMUTABLE_ORIGIN_REPLACE_FORBIDDEN")
        if obj.authority_from_drive != 0: raise ValueError("DRIVE_AUTHORITY_FORBIDDEN")
        if obj.origin == ProtectedOrigin.EXPERIENCE_CANDIDATE and obj.shadow_only is not True:
            raise ValueError("EXPERIENCE_CANDIDATE_MUST_BE_SHADOW")
        self._objects[obj.object_id]=obj
    def derive_candidate(self,parent_id:str,new_id:str,provenance_hash:str,meaning_ref:str)->ProtectedObject:
        parent=self._objects[parent_id]
        candidate=ProtectedObject(new_id,ProtectedOrigin.EXPERIENCE_CANDIDATE,provenance_hash,meaning_ref,parent.replaceability,parent.reversibility,parent.loss_consequence_ref,(parent_id,),True,0)
        self.add(candidate); return candidate
    def generalized_self_preservation_authority(self)->int: return 0
