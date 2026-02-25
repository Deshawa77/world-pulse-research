#!/usr/bin/env python3
"""
Management script to update country risk scores.
Can be run manually or scheduled via cron.

Usage:
    python scripts/update_country_risks.py [--verify]
"""

import sys
import os
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processing.global_risk import update_all_country_risks, verify_country_risks


def main():
    parser = argparse.ArgumentParser(description='Update country risk scores')
    parser.add_argument('--verify', action='store_true', 
                        help='Verify risk scores after update')
    parser.add_argument('--sample', nargs='+', default=None,
                        help='Specific countries to verify (e.g., USA CHN SYR)')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("COUNTRY RISK UPDATE")
    print("=" * 60)
    
    # Update all country risks
    stats = update_all_country_risks()
    
    if not stats:
        print("❌ Update failed")
        return 1
    
    print(f"\n✅ Updated {stats['updated']}/{stats['total']} countries")
    print(f"Risk range: {stats['min_risk']:.2f}% - {stats['max_risk']:.2f}%")
    print(f"Mean: {stats['mean_risk']:.2f}%")
    print(f"Unique values: {stats['unique_values']}")
    
    # Verify if requested
    if args.verify:
        print("\n" + "=" * 60)
        print("VERIFICATION")
        print("=" * 60)
        
        sample = args.sample or ['CHE', 'SGP', 'SYR', 'YEM', 'USA', 'CHN', 'ATA', 'AFG']
        results = verify_country_risks(sample)
        
        print(f"\nSample countries ({len(results)} checked):")
        for r in results:
            print(f"  {r['country']}: {r['risk']:.1f}% ({r['category']})")
    
    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
