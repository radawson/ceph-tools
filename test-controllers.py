#!/usr/bin/env python3
"""
RAID Controller Detection Test

Quick test to verify multi-controller detection before upgrading.
Run this first to see what controllers will be detected.

Usage:
    sudo python3 test-controllers.py
"""

import subprocess
import os
import sys

VERSION = "1.0.1"

def run_command(command, silent=False):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        if not silent:
            print(f"Command failed: {' '.join(command)}")
            print(f"Error: {e.stderr}")
        return None

def test_controllers():
    """Test for RAID controllers."""
    print("="*80)
    print("RAID CONTROLLER DETECTION TEST")
    print("="*80)
    print()
    
    # Method 1: Check lspci for controllers
    print("Method 1: Checking PCI bus for RAID controllers...")
    print()
    lspci_output = run_command(["lspci"], silent=True)
    pci_controllers = []
    
    if lspci_output:
        for line in lspci_output.split('\n'):
            if 'raid' in line.lower() or 'megaraid' in line.lower() or 'perc' in line.lower():
                print(f"  PCI Device: {line.strip()}")
                pci_controllers.append(line.strip())
    
    if pci_controllers:
        print(f"\n✓ Found {len(pci_controllers)} RAID controller(s) on PCI bus")
    else:
        print("  No RAID controllers found on PCI bus")
    
    print()
    print("="*80)
    print()
    
    # Method 2: Scan /dev/sg* devices with smartctl
    print("Method 2: Scanning /dev/sg* devices for controller access...")
    print()
    
    controllers = []
    
    # Try up to sg30 since you have many devices
    for i in range(31):
        sg_dev = f"/dev/sg{i}"
        
        if not os.path.exists(sg_dev):
            continue
        
        # Check if it's a RAID controller
        info = run_command(["smartctl", "-i", sg_dev], silent=True)
        
        if not info:
            continue
        
        # Check if it looks like a RAID controller
        is_raid = False
        controller_type = "Unknown"
        controller_model = "Unknown"
        
        # Look for RAID indicators in the output
        info_lower = info.lower()
        
        # Check for explicit RAID controller indicators
        if 'megaraid' in info_lower or 'perc' in info_lower:
            is_raid = True
        
        # Also check device type
        if 'enclosure' in info_lower or 'raid' in info_lower:
            is_raid = True
        
        # Parse model information
        for line in info.split('\n'):
            line_lower = line.lower()
            
            # Extract model information
            if 'product' in line_lower or 'device model' in line_lower:
                if ':' in line:
                    model = line.split(':', 1)[1].strip()
                    controller_model = model
                    
                    # Identify specific types
                    if 'h730' in model.lower():
                        controller_type = 'PERC H730'
                        is_raid = True
                    elif 'h830' in model.lower():
                        controller_type = 'PERC H830'
                        is_raid = True
                    elif 'h740' in model.lower():
                        controller_type = 'PERC H740'
                        is_raid = True
                    elif 'h840' in model.lower():
                        controller_type = 'PERC H840'
                        is_raid = True
                    elif 'perc' in model.lower():
                        controller_type = 'PERC (Unknown Model)'
                        is_raid = True
                    elif 'megaraid' in model.lower() or 'lsi' in model.lower() or '3108' in model.lower():
                        controller_type = 'MegaRAID/LSI'
                        is_raid = True
        
        if is_raid:
            controllers.append({
                'device': sg_dev,
                'type': controller_type,
                'model': controller_model,
                'index': i
            })
            
            print(f"✓ Found controller at {sg_dev}")
            print(f"  Type: {controller_type}")
            print(f"  Model: {controller_model}")
            print(f"  Index: {i}")
            print()
    
    if not controllers:
        print("  No controllers found via /dev/sg* scanning")
    
    print()
    print("="*80)
    print()
    
    # Method 3: Try to find controller by testing megaraid access
    print("Method 3: Testing MegaRAID driver access on /dev/sg* devices...")
    print()
    
    working_controllers = []
    
    # If we found controllers via smartctl, test them
    if controllers:
        for ctrl in controllers:
            sg_dev = ctrl['device']
            # Try to access drive 0 through this controller
            test_result = run_command(
                ["smartctl", "-i", "-d", "megaraid,0", sg_dev],
                silent=True
            )
            
            if test_result and 'serial' in test_result.lower():
                print(f"✓ {sg_dev} responds to megaraid commands")
                working_controllers.append(ctrl)
            else:
                print(f"✗ {sg_dev} does not respond to megaraid commands")
    
    # If no controllers found yet, try common sg devices
    if not working_controllers:
        print("  Testing common /dev/sg devices for megaraid access...")
        # Try sg24 (often controller) and a few others
        test_devices = [24, 0, 1, 2, 25, 26, 27]
        
        for i in test_devices:
            sg_dev = f"/dev/sg{i}"
            if not os.path.exists(sg_dev):
                continue
                
            test_result = run_command(
                ["smartctl", "-i", "-d", "megaraid,0", sg_dev],
                silent=True
            )
            
            if test_result and 'serial' in test_result.lower():
                print(f"  ✓ {sg_dev} responds to megaraid commands!")
                
                # Try to identify the controller
                ctrl_info = run_command(["smartctl", "-i", sg_dev], silent=True)
                controller_model = "Unknown"
                controller_type = "MegaRAID/LSI"
                
                if ctrl_info:
                    for line in ctrl_info.split('\n'):
                        if 'product' in line.lower() or 'device model' in line.lower():
                            if ':' in line:
                                controller_model = line.split(':', 1)[1].strip()
                
                working_controllers.append({
                    'device': sg_dev,
                    'type': controller_type,
                    'model': controller_model,
                    'index': i
                })
    
    print()
    print("="*80)
    
    print("="*80)
    print("SUMMARY")
    print("="*80)
    print()
    
    # Use working_controllers if we found any, otherwise fall back to controllers
    final_controllers = working_controllers if working_controllers else controllers
    
    if not final_controllers and not pci_controllers:
        print("❌ No RAID controllers detected!")
        print()
        print("Possible reasons:")
        print("  1. Not running as root/sudo")
        print("  2. No RAID controllers present")
        print("  3. Controllers not visible to OS")
        print()
        print("Try:")
        print("  - Run with sudo: sudo python3 test-controllers.py")
        print("  - Check hardware: lspci | grep -i raid")
        print("  - Check SCSI devices: ls -l /dev/sg*")
        return False
    
    if pci_controllers and not final_controllers:
        print("⚠️  PARTIAL DETECTION")
        print()
        print(f"✓ Found {len(pci_controllers)} controller(s) on PCI bus")
        print("❌ Could not access controllers via /dev/sg* devices")
        print()
        print("This usually means:")
        print("  1. Controllers are in RAID mode (drives presented directly)")
        print("  2. Need to find the controller passthrough device")
        print()
        print("Controllers detected on PCI bus:")
        for ctrl in pci_controllers:
            print(f"  • {ctrl}")
        print()
        print("Next steps:")
        print("  1. Try: sudo smartctl --scan")
        print("  2. Check: ls -l /dev/megaraid_sas_ioctl_node")
        print("  3. Test manual access: sudo smartctl -i -d megaraid,0 /dev/sgX")
        print("     (try sg0, sg24, sg25, sg26, sg27)")
        print()
        
        # Try to give specific device recommendations
        print("Recommended test commands:")
        for i in [24, 25, 26, 27, 0]:
            sg_dev = f"/dev/sg{i}"
            if os.path.exists(sg_dev):
                print(f"  sudo smartctl -i -d megaraid,0 {sg_dev}")
        
        return False
    
    print(f"✓ Detected {len(final_controllers)} accessible RAID controller(s)")
    print()
    
    for ctrl in final_controllers:
        print(f"  {ctrl['device']}: {ctrl['type']}")
    
    print()
    print("="*80)
    print("EXPECTED BEHAVIOR")
    print("="*80)
    print()
    
    if len(final_controllers) == 1:
        print("Your system has ONE accessible RAID controller.")
        print()
        print("The upgraded scripts will:")
        print("  ✓ Work correctly with your single controller")
        print("  ✓ Properly identify the controller type")
        print("  ✓ Scan all drives on this controller")
        print()
        print("No issues expected.")
    else:
        print(f"Your system has MULTIPLE accessible RAID controllers ({len(final_controllers)}).")
        print()
        print("The OLD scripts would:")
        print("  ❌ Only scan the first controller")
        print("  ❌ Miss drives on other controllers")
        print("  ❌ Show incorrect drive counts")
        print()
        print("The NEW scripts will:")
        print("  ✓ Scan ALL controllers")
        print("  ✓ Show drives from all controllers")
        print("  ✓ Correctly identify each controller type")
        print("  ✓ Provide complete drive inventory")
        print()
        print("⚠️  UPGRADE RECOMMENDED!")
    
    print()
    print("="*80)
    print("DRIVE SCAN TEST")
    print("="*80)
    print()
    
    total_drives = 0
    
    for ctrl in final_controllers:
        print(f"Testing {ctrl['device']} ({ctrl['type']})...")
        drives_found = 0
        
        # Quick test - just check first 10 slots
        for phy_id in range(10):
            info = run_command(
                ["smartctl", "-j", "-a", "-d", f"megaraid,{phy_id}", ctrl['device']],
                silent=True
            )
            
            if info and 'serial_number' in info:
                drives_found += 1
        
        if drives_found > 0:
            print(f"  ✓ Found at least {drives_found} drive(s) in first 10 slots")
            print(f"  → Full scan will check all 32 slots")
        else:
            print(f"  ℹ️  No drives detected in first 10 slots")
            print(f"  → May have drives in higher slots or empty controller")
        
        total_drives += drives_found
        print()
    
    if total_drives == 0:
        print("⚠️  Warning: No drives detected on any controller")
        print()
        print("This could mean:")
        print("  1. No drives are installed")
        print("  2. Drives are in slots 10-32 (not tested here)")
        print("  3. Permission or access issues")
        print()
        print("Full scan will check all 32 slots on each controller.")
    else:
        print(f"✓ Quick test found {total_drives} drive(s)")
        print()
        print("Full scan will provide complete inventory.")
    
    print()
    print("="*80)
    print("NEXT STEPS")
    print("="*80)
    print()
    
    if len(final_controllers) > 1:
        print("1. UPGRADE RECOMMENDED - You have multiple controllers")
        print("   → Read MULTI_CONTROLLER_UPGRADE.md")
        print("   → Follow installation instructions")
        print()
        print("2. After upgrade, run:")
        print("   → sudo ./check-osd-plain.py")
        print()
        print("3. Verify output shows all controllers:")
        for ctrl in final_controllers:
            print(f"   → Should see: {ctrl['device']}: {ctrl['type']}")
    else:
        print("1. Upgrade still beneficial:")
        print("   → Better controller identification")
        print("   → Bug fixes")
        print("   → Enhanced output")
        print()
        print("2. After upgrade, run:")
        print("   → sudo ./check-osd-plain.py")
        print()
        print("3. Verify improved output")
    
    print()
    return True

def main():
    if os.geteuid() != 0:
        print("="*80)
        print("ERROR: This script must be run with sudo")
        print("="*80)
        print()
        print("Usage: sudo python3 test-controllers.py")
        print()
        sys.exit(1)
    
    # Check for smartctl
    smartctl_check = run_command(["which", "smartctl"], silent=True)
    if not smartctl_check:
        print("="*80)
        print("ERROR: smartctl not found")
        print("="*80)
        print()
        print("Please install smartmontools:")
        print("  Ubuntu/Debian: sudo apt install smartmontools")
        print("  RHEL/CentOS:   sudo yum install smartmontools")
        print()
        sys.exit(1)
    
    success = test_controllers()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()