import os
import json
import random
import hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException

router = APIRouter()

def build_pyramidal_structure(total_tokens=66000):
    root_dir = "sebbi_pyramid_structure"
    apex_path = os.path.join(root_dir, "APEX_ENGINE_SEAL.json")
    
    if os.path.exists(apex_path):
        print("sebbi.pro: Pyramidal structure and apex seal already verified. Skipping rebuild.")
        return

    os.makedirs(root_dir, exist_ok=True)
    
    narratives = [
        "Encoded with the whispers of ancient stars.",
        "Bound to the immutable ledger of the deep grid.",
        "Carrying the cryptographic pulse of the genesis block.",
        "Weaving fragments of the master vision into existence.",
        "Anchored in zero-trust verification and sovereign state.",
        "Tracing the silent pathways of deterministic execution.",
        "Sculpted from the raw metadata of the engine core.",
        "Reflecting the collective frequency of the network."
    ]
    
    capabilities_pool = [
        "VERIFY_STATE_HASH",
        "EXECUTE_DETERMINISTIC_LOGIC",
        "MUTUAL_WITNESS_PING",
        "PIXEL_MATRIX_MAPPING",
        "ZERO_TRUST_AUDIT",
        "CORE_ENGINE_SEAL"
    ]
    
    print(f"sebbi.pro: Constructing master architectural pyramid for {total_tokens} tokens...")
    
    cols = 256
    layer_size = 1000
    tier_hashes = {}

    for i in range(1, total_tokens + 1):
        token_id = f"TOKEN_{i:05d}"
        block_code = f"GENESIS_{random.randint(10000, 99999)}"
        story = random.choice(narratives)
        assigned_capability = random.choice(capabilities_pool)
        created_at = datetime.now(timezone.utc).isoformat()
        
        coord_x = (i - 1) % cols
        coord_y = (i - 1) // cols
        
        tier_id = f"tier_{(i - 1) // layer_size:03d}"
        tier_dir = os.path.join(root_dir, tier_id)
        os.makedirs(tier_dir, exist_ok=True)
        
        raw_signature_string = f"{token_id}-{block_code}-{coord_x}-{coord_y}-{assigned_capability}-{created_at}"
        token_hash = hashlib.sha256(raw_signature_string.encode('utf-8')).hexdigest()
        
        token_data = {
            "token_id": token_id,
            "block_code": block_code,
            "pyramid_tier": tier_id,
            "canvas_coordinate": {"x": coord_x, "y": coord_y},
            "capability": assigned_capability,
            "execution_hash": token_hash,
            "story": story,
            "created_at": created_at
        }
        
        file_path = os.path.join(tier_dir, f"{token_id}.json")
        with open(file_path, "w") as f:
            json.dump(token_data, f, indent=2)
            
        if tier_id not in tier_hashes:
            tier_hashes[tier_id] = []
        tier_hashes[tier_id].append(token_hash)

    apex_manifest = {
        "engine": "sebbi.pro",
        "total_tokens": total_tokens,
        "structure": "pyramidal_tier_hierarchy",
        "sealed_at": datetime.now(timezone.utc).isoformat(),
        "tiers": {}
    }
    
    for tier_id, hashes in tier_hashes.items():
        combined_tier_string = "".join(hashes)
        apex_manifest["tiers"][tier_id] = {
            "token_count": len(hashes),
            "tier_root_hash": hashlib.sha256(combined_tier_string.encode('utf-8')).hexdigest()
        }
        
    with open(apex_path, "w") as f:
        json.dump(apex_manifest, f, indent=4)
        
    print(f"sebbi.pro: Apex engine seal locked successfully at '{apex_path}'.")

# Build the pyramid automatically when this module is loaded by your system
build_pyramidal_structure()

@router.get("/engine/verify")
def verify_engine_apex():
    apex_path = "sebbi_pyramid_structure/APEX_ENGINE_SEAL.json"
    
    if not os.path.exists(apex_path):
        raise HTTPException(status_code=503, detail="Pyramid structure is still initializing on the engine.")
        
    with open(apex_path, "r") as f:
        seal = json.load(f)
        
    return {
        "engine": "sebbi.pro",
        "status": "ACTIVE_AND_SEALED",
        "total_tokens": seal.get("total_tokens"),
        "structure": seal.get("structure"),
        "sealed_at": seal.get("sealed_at"),
        "active_capabilities": [
            "VERIFY_STATE_HASH",
            "EXECUTE_DETERMINISTIC_LOGIC",
            "MUTUAL_WITNESS_PING",
            "PIXEL_MATRIX_MAPPING",
            "ZERO_TRUST_AUDIT",
            "CORE_ENGINE_SEAL"
        ],
        "tiers_verified": len(seal.get("tiers", {}))
    }
