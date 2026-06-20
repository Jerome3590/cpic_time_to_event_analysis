#!/usr/bin/env python3
"""Check which model_events.parquet files in S3 have controls."""

import subprocess
import sys
import tempfile
import os
import pandas as pd
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
try:
    from py_helpers.constants import PROJECT_SLUG
except ImportError:
    PROJECT_SLUG = "cpic_time_to_event"

def check_s3_file_controls(s3_path, profile='mushin'):
    """Check if an S3 parquet file has controls."""
    # Create temp file
    with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as tmp:
        temp_file = tmp.name
    
    try:
        # Download file
        result = subprocess.run(
            ['aws', 's3', 'cp', s3_path, temp_file, '--profile', profile],
            capture_output=True, text=True
        )
        
        if result.returncode != 0:
            return {'error': 'Download failed', 'stderr': result.stderr}
        
        # Check controls using pandas
        import pandas as pd
        df = pd.read_parquet(temp_file)
        
        if 'target' not in df.columns:
            return {'error': 'No target column found'}
        
        n_controls = int((df['target'] == 0).sum())
        n_cases = int((df['target'] == 1).sum())
        
        return {
            'has_controls': n_controls > 0,
            'n_controls': n_controls,
            'n_cases': n_cases
        }
    finally:
        # Clean up
        if os.path.exists(temp_file):
            os.unlink(temp_file)


def main():
    cohorts = ['falls', 'ed']
    age_bands = ['65-74', '75-84']
    
    print('=== Checking model_events.parquet files in S3 for controls ===')
    print('')
    
    results = {}
    for cohort in cohorts:
        for age_band in age_bands:
            key = f'{cohort}/{age_band}'
            s3_path = f's3://pgxdatalake/gold/{PROJECT_SLUG}/cohorts/input_model_data/cohort_name={cohort}/age_band={age_band}/model_events.parquet'
            
            # Check if file exists first
            ls_result = subprocess.run(
                ['aws', 's3', 'ls', s3_path, '--profile', 'mushin'],
                capture_output=True, text=True
            )
            
            if ls_result.returncode != 0:
                results[key] = {'error': 'File not found'}
                print(f'{key}: [NOT FOUND]')
                continue
            
            print(f'Checking {key}...', end=' ', flush=True)
            result = check_s3_file_controls(s3_path)
            
            if 'error' in result:
                results[key] = result
                print(f'[ERROR] {result["error"]}')
            else:
                results[key] = result
                status = '[OK]' if result['has_controls'] else '[NO CONTROLS]'
                print(f'{status} Controls: {result["n_controls"]:,}, Cases: {result["n_cases"]:,}')
    
    print('')
    print('=== Summary ===')
    print('')
    
    valid = [k for k, r in results.items() if r.get('has_controls', False)]
    invalid = [k for k, r in results.items() if not r.get('has_controls', False) and 'error' not in r]
    missing = [k for k, r in results.items() if 'error' in r and r.get('error') == 'File not found']
    
    print(f'Valid (with controls): {len(valid)}')
    for k in valid:
        r = results[k]
        print(f'  [1] {k}: {r["n_controls"]:,} controls, {r["n_cases"]:,} cases')
    
    if invalid:
        print(f'')
        print(f'Invalid (no controls): {len(invalid)}')
        for k in invalid:
            r = results[k]
            print(f'  [X] {k}: {r.get("n_controls", 0):,} controls, {r.get("n_cases", 0):,} cases')
    
    if missing:
        print(f'')
        print(f'Missing: {len(missing)}')
        for k in missing:
            print(f'  - {k}')


if __name__ == '__main__':
    main()
