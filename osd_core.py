#!/usr/bin/env python3
"""
Ceph OSD Drive Monitor - Core Module

Pure Python data collection with NO external dependencies.
This module handles all the data gathering and can be imported
by different display/export frontends.

Usage:
    from osd_core import OSDMonitor
    
    monitor = OSDMonitor()
    data = monitor.scan()
    
    # data contains all drive information
"""

VERSION = "1.0.2"

import subprocess
import json
import sys
import os
import re
from datetime import datetime
from pathlib import Path

DEBUG = True

def debug_print(message):
    """Print debug messages if DEBUG is enabled."""
    if DEBUG:
        print(f"[DEBUG] {message}", file=sys.stderr)

def run_command(command, is_json=False, silent=False):
    """Helper function to run shell commands and return output."""
    try:
        if len(command) > 0 and command[0] in ['ceph', 'pvs', 'lvs', 'systemctl'] and command[0] != 'sudo':
            command.insert(0, 'sudo')

        if not silent:
            debug_print(f"Running: {' '.join(command)}")

        result = subprocess.run(command, capture_output=True, text=True, check=True)

        if is_json:
            return json.loads(result.stdout)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        if not silent:
            debug_print(f"Command failed: {' '.join(command)}")
            debug_print(f"Error: {e.stderr}")
        return None
    except json.JSONDecodeError as e:
        debug_print(f"JSON decode failed: {e}")
        return None

class OSDMonitor:
    """Core OSD monitoring functionality - pure Python, no dependencies."""
    
    def __init__(self):
        self.controllers = []  # Changed from single controller_dev
        self.controller_info = {}
        self.drives = {}
        self.osds = {}
        self.osd_to_drive = {}
        self.osd_status = {}
        self.systemd_status = {}
        self.osd_perf = {}
        self.scan_timestamp = None
    
    def find_raid_controllers(self):
        """Find ALL RAID controllers and JBOD enclosures."""
        debug_print("Looking for RAID controller(s)...")
        controllers = []
        seen_serials = set()  # Track controller serials to avoid duplicates
        
        # Scan wider range to catch JBOD enclosures (like MD1400 at sg24)
        for i in range(30):
            sg_dev = f"/dev/sg{i}"
            if os.path.exists(sg_dev):
                info = run_command(["smartctl", "-i", sg_dev], is_json=False, silent=True)
                
                if not info:
                    continue
                
                info_lower = info.lower()
                
                # Check if this is a controller/enclosure we want to track
                is_raid = 'megaraid' in info_lower or 'raid' in info_lower or 'perc' in info_lower
                is_jbod = 'md1400' in info_lower or 'md1200' in info_lower or 'jbod' in info_lower
                is_enclosure = 'enclosure' in info_lower
                
                if is_raid or is_jbod or is_enclosure:
                    controller_type = 'Unknown'
                    controller_model = 'Unknown'
                    controller_serial = None
                    is_megaraid_type = False
                    
                    for line in info.split('\n'):
                        line_lower = line.lower()
                        if 'product' in line_lower or 'device model' in line_lower:
                            if ':' in line:
                                model = line.split(':', 1)[1].strip()
                                controller_model = model
                                
                                # Check for JBOD/SAS expander enclosures
                                if 'md1400' in model.lower():
                                    controller_type = 'MD1400 JBOD'
                                    is_megaraid_type = False
                                elif 'md1200' in model.lower():
                                    controller_type = 'MD1200 JBOD'
                                    is_megaraid_type = False
                                # Identify specific Dell PERC models
                                elif 'h730' in model.lower():
                                    controller_type = 'PERC H730'
                                    is_megaraid_type = True
                                elif 'h830' in model.lower():
                                    controller_type = 'PERC H830'
                                    is_megaraid_type = True
                                elif 'h740' in model.lower():
                                    controller_type = 'PERC H740'
                                    is_megaraid_type = True
                                elif 'h840' in model.lower():
                                    controller_type = 'PERC H840'
                                    is_megaraid_type = True
                                elif 'perc' in model.lower():
                                    controller_type = 'PERC'
                                    is_megaraid_type = True
                                elif 'megaraid' in model.lower() or 'lsi' in model.lower():
                                    controller_type = 'MegaRAID/LSI'
                                    is_megaraid_type = True
                        
                        elif 'serial number' in line_lower:
                            if ':' in line:
                                controller_serial = line.split(':', 1)[1].strip()
                    
                    # Skip duplicate controllers (same serial = same physical controller)
                    if controller_serial and controller_serial in seen_serials:
                        debug_print(f"{sg_dev}: Duplicate controller with S/N {controller_serial}, skipping")
                        continue
                    
                    if controller_serial:
                        seen_serials.add(controller_serial)
                    
                    controllers.append({
                        'device': sg_dev,
                        'type': controller_type,
                        'model': controller_model,
                        'index': i,
                        'is_megaraid': is_megaraid_type,
                        'serial': controller_serial
                    })
                    debug_print(f"Found RAID controller at {sg_dev}: {controller_type} ({controller_model})")
        
        if not controllers:
            debug_print("No RAID controllers found, defaulting to /dev/sg6")
            controllers = [{
                'device': '/dev/sg6',
                'type': 'Unknown',
                'model': 'Unknown',
                'index': 6
            }]
        else:
            debug_print(f"Total controllers found: {len(controllers)}")
        
        return controllers
    
    @staticmethod
    def build_scsi_address_from_phy(phy_id, controller_index):
        """
        Build SCSI address from PHY ID.
        For most RAID controllers: [Host:Channel:Target:LUN]
        - Host: Controller index (0 for first, 1 for second, etc.)
        - Channel: Usually 0
        - Target: Usually equals PHY ID or slot number
        - LUN: Usually 0
        """
        host = controller_index  # Use actual controller index
        channel = 0  # Most controllers use channel 0
        target = phy_id  # PHY ID typically maps to target
        lun = 0  # Single LUN per drive
        
        return f"{host}:{channel}:{target}:{lun}"
    
    @staticmethod
    def extract_smart_details(smart_info):
        """Extract key SMART attributes from smartctl JSON output."""
        details = {
            'temperature': None,
            'power_on_hours': None,
            'reallocated_sectors': None,
            'pending_sectors': None,
            'uncorrectable': None,
            'load_cycle_count': None,
        }
        
        if 'temperature' in smart_info:
            details['temperature'] = smart_info['temperature'].get('current')
        
        if 'ata_smart_attributes' in smart_info and 'table' in smart_info['ata_smart_attributes']:
            for attr in smart_info['ata_smart_attributes']['table']:
                attr_id = attr.get('id')
                raw_value = attr.get('raw', {}).get('value', 0)
                
                if attr_id == 5:
                    details['reallocated_sectors'] = raw_value
                elif attr_id == 9:
                    details['power_on_hours'] = raw_value
                elif attr_id == 193:
                    details['load_cycle_count'] = raw_value
                elif attr_id == 197:
                    details['pending_sectors'] = raw_value
                elif attr_id == 198:
                    details['uncorrectable'] = raw_value
        
        if 'scsi_grown_defect_list' in smart_info:
            details['reallocated_sectors'] = smart_info.get('scsi_grown_defect_list', 0)
        
        return details
    
    @staticmethod
    def format_size_bytes(size_bytes):
        """Convert bytes to human-readable format."""
        if not size_bytes:
            return None
        
        try:
            size_bytes = int(size_bytes)
        except (ValueError, TypeError):
            return None
        
        if size_bytes >= 1e12:
            return f"{size_bytes / 1e12:.1f}T"
        elif size_bytes >= 1e9:
            return f"{size_bytes / 1e9:.0f}G"
        else:
            return f"{size_bytes / 1e6:.0f}M"
    
    def scan_jbod_enclosure(self, controller, seen_serials):
        """
        Scan a JBOD enclosure by finding its SCSI host and enumerating targets.
        
        Returns:
            dict: drives found in this enclosure
        """
        drives = {}
        controller_dev = controller['device']
        controller_type = controller['type']
        controller_index = controller['index']
        
        # Get the SCSI host number from lsscsi
        lsscsi_output = run_command(["lsscsi"], is_json=False, silent=True)
        if not lsscsi_output:
            return drives
        
        # Find all SCSI addresses for this host (controller_index)
        # Looking for pattern: [24:0:26:0] for drives on host 24
        targets_found = set()
        for line in lsscsi_output.splitlines():
            match = re.match(r'\[(\d+):(\d+):(\d+):(\d+)\]', line)
            if match:
                host = int(match.group(1))
                channel = int(match.group(2))
                target = int(match.group(3))
                lun = int(match.group(4))
                
                if host == controller_index:
                    targets_found.add((channel, target, lun))
        
        debug_print(f"JBOD {controller_dev}: Found {len(targets_found)} targets on host {controller_index}")
        
        # Now scan each target we found
        for channel, target, lun in sorted(targets_found):
            scsi_addr = f"{controller_index}:{channel}:{target}:{lun}"
            
            # Find the /dev/sg device for this SCSI address
            sg_device = None
            for line in lsscsi_output.splitlines():
                if f"[{scsi_addr}]" in line and '/dev/sg' in line:
                    match = re.search(r'/dev/sg\d+', line)
                    if match:
                        sg_device = match.group(0)
                        break
            
            if not sg_device:
                continue
            
            # Query this drive directly (not through megaraid passthrough)
            info = run_command(["smartctl", "-j", "-a", sg_device], is_json=True, silent=True)
            
            if info and 'serial_number' in info:
                serial = info['serial_number']
                
                if serial in seen_serials:
                    continue
                
                seen_serials.add(serial)
                
                model = info.get('model_name', info.get('model_family', 'Unknown'))
                vendor = info.get('vendor', '')
                
                if not vendor and model:
                    vendor_match = re.match(r'^(\w+)', model)
                    if vendor_match:
                        vendor = vendor_match.group(1)
                
                health_passed = info.get('smart_status', {}).get('passed', False)
                smart_details = self.extract_smart_details(info)
                
                size = None
                if 'user_capacity' in info:
                    size_info = info['user_capacity']
                    if isinstance(size_info, dict) and 'bytes' in size_info:
                        size = self.format_size_bytes(size_info['bytes'])
                
                drives[serial] = {
                    'phy_id': target,  # Use target ID as PHY
                    'serial': serial,
                    'model': model,
                    'vendor': vendor,
                    'health_hw': 'OK' if health_passed else 'FAIL',
                    'smart_details': smart_details,
                    'current_device': None,
                    'scsi_address': scsi_addr,
                    'size': size,
                    'controller': controller_type,
                    'controller_device': controller_dev,
                }
                
                debug_print(f"Controller {controller_dev} PHY {target}: {model} S/N:{serial} SCSI:{scsi_addr} Size:{size or 'N/A'}")
        
        return drives
    
    def scan_physical_drives(self, progress_callback=None):
        """
        Scan ALL RAID controllers for physical drives.
        
        Args:
            progress_callback: Optional function(current, total, message) for progress updates
        
        Returns:
            dict: {serial: {phy_id, serial, model, vendor, health_hw, smart_details, size, scsi_address, controller}}
        """
        drives = {}
        slots_per_controller = 32
        total_slots = len(self.controllers) * slots_per_controller
        current_slot = 0
        
        # Track which serials we've seen to avoid duplicates
        seen_serials = set()
        
        for controller in self.controllers:
            controller_dev = controller['device']
            controller_type = controller['type']
            controller_index = controller['index']
            is_megaraid = controller.get('is_megaraid', True)
            
            debug_print(f"Scanning controller {controller_dev} ({controller_type})")
            
            # JBOD enclosures need special handling
            if not is_megaraid:
                jbod_drives = self.scan_jbod_enclosure(controller, seen_serials)
                drives.update(jbod_drives)
                continue
            
            # For MegaRAID controllers, use the megaraid passthrough
            for phy_id in range(slots_per_controller):
                if progress_callback:
                    progress_callback(current_slot, total_slots, 
                                    f"Scanning {controller_dev} PHY {phy_id}")
                current_slot += 1
                
                info = run_command(
                    ["smartctl", "-j", "-a", "-d", f"megaraid,{phy_id}", controller_dev],
                    is_json=True, 
                    silent=True
                )

                if info and 'serial_number' in info:
                    serial = info['serial_number']
                    
                    # Skip if we've already seen this serial number
                    # (multiple sg devices may be passthrough to same controller)
                    if serial in seen_serials:
                        debug_print(f"Controller {controller_dev} PHY {phy_id}: Duplicate serial {serial} (already found on another controller passthrough)")
                        continue
                    
                    seen_serials.add(serial)
                    
                    model = info.get('model_name', info.get('model_family', 'Unknown'))
                    vendor = info.get('vendor', '')

                    if not vendor and model:
                        vendor_match = re.match(r'^(\w+)', model)
                        if vendor_match:
                            vendor = vendor_match.group(1)

                    health_passed = info.get('smart_status', {}).get('passed', False)
                    smart_details = self.extract_smart_details(info)
                    
                    size = None
                    if 'user_capacity' in info:
                        size_info = info['user_capacity']
                        if isinstance(size_info, dict) and 'bytes' in size_info:
                            size = self.format_size_bytes(size_info['bytes'])
                    
                    scsi_address = self.build_scsi_address_from_phy(phy_id, controller_index)

                    drives[serial] = {
                        'phy_id': phy_id,
                        'serial': serial,
                        'model': model,
                        'vendor': vendor,
                        'health_hw': 'OK' if health_passed else 'FAIL',
                        'smart_details': smart_details,
                        'current_device': None,
                        'scsi_address': scsi_address,
                        'size': size,
                        'controller': controller_type,
                        'controller_device': controller_dev,
                    }

                    debug_print(f"Controller {controller_dev} PHY {phy_id}: {model} S/N:{serial} SCSI:{scsi_address} Size:{size or 'N/A'}")
        
        if progress_callback:
            progress_callback(total_slots, total_slots, "Scan complete")
        
        debug_print(f"Found {len(drives)} unique physical drives across {len(self.controllers)} controller(s)")
        return drives
    
    def map_drives_to_devices(self, drives):
        """Map physical drives to current /dev/sdX device names."""
        lsscsi_output = run_command(["lsscsi"], is_json=False, silent=True)

        if lsscsi_output:
            for line in lsscsi_output.splitlines():
                match = re.match(r'\[([^\]]+)\]\s+(\w+)\s+(\S+)\s+(\S+)\s+\S+\s+(/dev/\w+)', line)
                if match:
                    scsi_addr = match.group(1)
                    dev_type = match.group(2)
                    vendor = match.group(3)
                    model = match.group(4)
                    dev_path = match.group(5)
                    dev_name = dev_path.replace('/dev/', '')

                    if dev_type != 'disk':
                        continue

                    info = run_command(["smartctl", "-j", "-i", dev_path], is_json=True, silent=True)
                    if info and 'serial_number' in info:
                        serial = info['serial_number']

                        if serial in drives:
                            drives[serial]['current_device'] = dev_name
                            drives[serial]['scsi_address'] = scsi_addr

                            if vendor and model:
                                drives[serial]['model'] = f"{vendor} {model}"

                            lsblk_info = run_command(
                                ["lsblk", "-J", "-o", "NAME,SIZE", dev_path],
                                is_json=True, 
                                silent=True
                            )
                            if lsblk_info and 'blockdevices' in lsblk_info:
                                lsblk_size = lsblk_info['blockdevices'][0].get('size', None)
                                if lsblk_size:
                                    drives[serial]['size'] = lsblk_size

                            debug_print(f"{dev_name}: SCSI {scsi_addr}, Serial {serial}, "
                                      f"PHY {drives[serial]['phy_id']}, Size {drives[serial]['size']}")

        mapped = sum(1 for d in drives.values() if d.get('current_device'))
        unmapped = len(drives) - mapped
        debug_print(f"Mapped {mapped}/{len(drives)} physical drives to device names")
        if unmapped > 0:
            debug_print(f"{unmapped} drive(s) not visible to OS")
        
        return drives
    
    def get_ceph_osds(self):
        """Get ALL Ceph OSDs metadata."""
        metadata = run_command(["ceph", "osd", "metadata"], is_json=True)
        if not metadata:
            debug_print("ERROR: Could not retrieve Ceph OSD metadata!")
            return {}

        osds = {}
        for osd in metadata:
            osd_id = str(osd.get('id', ''))
            osds[osd_id] = osd
            debug_print(f"OSD {osd_id}: host={osd.get('hostname', 'unknown')} "
                       f"device_ids={osd.get('device_ids', 'N/A')}")

        debug_print(f"Found {len(osds)} OSDs in cluster")
        return osds
    
    def get_osd_performance(self):
        """Get OSD performance metrics (latency)."""
        perf = {}
        output = run_command(["ceph", "osd", "perf"], is_json=False, silent=True)
        
        if output:
            for line in output.splitlines():
                if 'osd' in line and 'commit_latency' in line:
                    continue
                
                match = re.match(r'\s*(\d+)\s+(\d+)\s+(\d+)', line)
                if match:
                    osd_id = match.group(1)
                    commit_lat = int(match.group(2))
                    apply_lat = int(match.group(3))
                    perf[osd_id] = {
                        'commit_latency_ms': commit_lat,
                        'apply_latency_ms': apply_lat
                    }
                    debug_print(f"OSD {osd_id}: commit={commit_lat}ms, apply={apply_lat}ms")
        
        debug_print(f"Got performance data for {len(perf)} OSDs")
        return perf
    
    @staticmethod
    def parse_device_id(device_ids_string):
        """Parse device_ids string from Ceph metadata."""
        if not device_ids_string:
            return None

        for part in device_ids_string.split(','):
            if '=' not in part:
                continue

            device_name, identifier = part.split('=', 1)
            device_name = device_name.strip()
            identifier = identifier.strip()

            parts = identifier.split('_')
            if len(parts) >= 3:
                vendor = parts[0]
                serial = parts[-1]
                model = '_'.join(parts[1:-1])

                return {
                    'device_name': device_name,
                    'vendor': vendor,
                    'model': model,
                    'serial': serial,
                    'full_id': identifier
                }

        return None
    
    def match_drives_to_osds(self, drives, osds):
        """Match local physical drives to OSDs using device_ids."""
        osd_to_drive = {}

        for osd_id, osd_meta in osds.items():
            device_ids = osd_meta.get('device_ids', '')
            hostname = osd_meta.get('hostname', 'unknown')

            parsed = self.parse_device_id(device_ids)
            if not parsed:
                debug_print(f"OSD {osd_id}: Could not parse device_ids: {device_ids}")
                continue

            osd_serial = parsed['serial']

            if osd_serial in drives:
                osd_to_drive[osd_id] = osd_serial
                debug_print(f"âœ“ OSD {osd_id} (on {hostname}): Matched to local drive")
                debug_print(f"  Serial: {osd_serial}, PHY: {drives[osd_serial]['phy_id']}, "
                           f"Device: {drives[osd_serial].get('current_device', 'N/A')}")
            else:
                debug_print(f"OSD {osd_id} (on {hostname}): Serial {osd_serial} not found locally")

        debug_print(f"Matched {len(osd_to_drive)} OSDs to local drives")
        return osd_to_drive
    
    def get_osd_status(self):
        """Get OSD status information: up/down and in/out."""
        status_map = {}

        tree_output = run_command(["ceph", "osd", "tree"], is_json=False)
        if tree_output:
            for line in tree_output.splitlines():
                match = re.match(r'\s*(\d+)\s+\w+\s+[\d\.]+\s+osd\.\d+\s+(\w+)\s+.*', line)
                if match:
                    osd_id = match.group(1)
                    up_status = match.group(2)
                    status_map[osd_id] = {
                        'up': (up_status == 'up'),
                        'in': None
                    }

        dump_output = run_command(["ceph", "osd", "dump"], is_json=False)
        if dump_output:
            for line in dump_output.splitlines():
                match = re.search(r'osd\.(\d+)\s+(\w+)\s+(\w+)', line)
                if match:
                    osd_id = match.group(1)
                    in_status = match.group(3)
                    if osd_id in status_map:
                        status_map[osd_id]['in'] = (in_status == 'in')

        debug_print(f"Got status for {len(status_map)} OSDs")
        return status_map
    
    def check_systemd_status(self, osd_ids):
        """Check systemd service status for OSDs."""
        systemd_status = {}

        for osd_id in osd_ids:
            service_name = f"ceph-osd@{osd_id}.service"
            result = run_command(["systemctl", "is-active", service_name],
                               is_json=False, silent=True)

            if result and result.strip() in ['active', 'activating']:
                systemd_status[osd_id] = 'active'
                debug_print(f"OSD {osd_id} systemd: active")
            elif result and result.strip() in ['inactive', 'failed', 'deactivating']:
                systemd_status[osd_id] = 'inactive'
                debug_print(f"OSD {osd_id} systemd: inactive ({result.strip()})")
            else:
                systemd_status[osd_id] = 'unknown'
                debug_print(f"OSD {osd_id} systemd: unknown")

        return systemd_status
    
    def scan(self, progress_callback=None):
        """
        Complete scan of all drives and OSDs.
        
        Args:
            progress_callback: Optional function(current, total, message) for progress updates
        
        Returns:
            dict: Complete scan data including drives, osds, status, performance
        """
        self.scan_timestamp = datetime.now().isoformat()
        
        # Find all controllers
        self.controllers = self.find_raid_controllers()
        
        # Build controller info summary
        self.controller_info = {
            'count': len(self.controllers),
            'controllers': self.controllers
        }
        
        # Scan physical drives from all controllers
        self.drives = self.scan_physical_drives(progress_callback)
        if not self.drives:
            return None
        
        # Map to devices
        self.drives = self.map_drives_to_devices(self.drives)
        
        # Get Ceph data
        self.osds = self.get_ceph_osds()
        if not self.osds:
            return None
        
        self.osd_perf = self.get_osd_performance()
        self.osd_to_drive = self.match_drives_to_osds(self.drives, self.osds)
        self.osd_status = self.get_osd_status()
        self.systemd_status = self.check_systemd_status(self.osd_to_drive.keys())
        
        return {
            'timestamp': self.scan_timestamp,
            'controller': self.controller_info,
            'drives': self.drives,
            'osds': self.osds,
            'osd_to_drive': self.osd_to_drive,
            'osd_status': self.osd_status,
            'systemd_status': self.systemd_status,
            'osd_perf': self.osd_perf,
        }
    
    @staticmethod
    def format_age(power_on_hours):
        """Format power-on hours as human readable age."""
        if not power_on_hours:
            return "N/A"
        
        years = power_on_hours / 8760
        if years >= 1:
            return f"{years:.1f}y"
        else:
            months = power_on_hours / 730
            return f"{months:.0f}mo"
    
    @staticmethod
    def analyze_health(data):
        """
        Analyze scan data for health issues.
        
        Returns:
            dict: {
                'smart_problems': list of drives with SMART errors,
                'high_latency': list of OSDs with high latency,
                'high_temp': list of drives with high temperature,
                'down_osds': list of down OSDs,
                'available_drives': list of unmapped drives
            }
        """
        issues = {
            'smart_problems': [],
            'high_latency': [],
            'high_temp': [],
            'down_osds': [],
            'available_drives': []
        }
        
        drives = data['drives']
        osd_to_drive = data['osd_to_drive']
        osd_status = data['osd_status']
        osd_perf = data['osd_perf']
        
        # Check each drive
        for serial, drive in drives.items():
            smart = drive.get('smart_details', {})
            
            # Find OSD for this drive
            osd_id = None
            for oid, drv_serial in osd_to_drive.items():
                if drv_serial == serial:
                    osd_id = oid
                    break
            
            # SMART issues
            if ((smart.get('reallocated_sectors') or 0) > 0 or 
                (smart.get('pending_sectors') or 0) > 0 or 
                (smart.get('uncorrectable') or 0) > 0):
                issues['smart_problems'].append({
                    'osd_id': osd_id,
                    'drive': drive,
                    'serial': serial
                })
            
            # High temperature
            temp = smart.get('temperature')
            if temp and temp > 45:
                issues['high_temp'].append({
                    'osd_id': osd_id,
                    'drive': drive,
                    'serial': serial,
                    'temperature': temp
                })
            
            # Available drives
            if not osd_id and drive.get('current_device'):
                issues['available_drives'].append({
                    'drive': drive,
                    'serial': serial
                })
        
        # Check OSD performance
        for osd_id, perf in osd_perf.items():
            if perf.get('commit_latency_ms', 0) > 100:
                serial = osd_to_drive.get(osd_id)
                drive = drives.get(serial) if serial else None
                issues['high_latency'].append({
                    'osd_id': osd_id,
                    'latency': perf['commit_latency_ms'],
                    'drive': drive,
                    'serial': serial
                })
        
        # Check OSD status
        for osd_id, status in osd_status.items():
            if not status.get('up', True):
                serial = osd_to_drive.get(osd_id)
                drive = drives.get(serial) if serial else None
                issues['down_osds'].append({
                    'osd_id': osd_id,
                    'drive': drive,
                    'serial': serial
                })
        
        return issues

# Standalone test
if __name__ == "__main__":
    if os.geteuid() != 0:
        print("ERROR: This script must be run with sudo")
        sys.exit(1)
    
    print("Testing OSD Core Module (Pure Python)")
    print("=" * 80)
    
    monitor = OSDMonitor()
    
    def progress(current, total, message):
        percent = (current / total) * 100
        print(f"Progress: {percent:.0f}% - {message}")
    
    data = monitor.scan(progress_callback=progress)
    
    if data:
        print("\nScan completed successfully!")
        print(f"Timestamp: {data['timestamp']}")
        print(f"Drives found: {len(data['drives'])}")
        print(f"OSDs found: {len(data['osds'])}")
        print(f"Local OSDs: {len(data['osd_to_drive'])}")
        
        issues = OSDMonitor.analyze_health(data)
        print(f"\nHealth Analysis:")
        print(f"  SMART problems: {len(issues['smart_problems'])}")
        print(f"  High latency: {len(issues['high_latency'])}")
        print(f"  High temperature: {len(issues['high_temp'])}")
        print(f"  Down OSDs: {len(issues['down_osds'])}")
        print(f"  Available drives: {len(issues['available_drives'])}")
    else:
        print("\nScan failed!")
        sys.exit(1)