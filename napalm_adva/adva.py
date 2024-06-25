# -*- coding: utf-8 -*-
# Copyright 2016 Dravetech AB. All rights reserved.
#
# The contents of this file are licensed under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with the
# License. You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.

"""
Napalm driver for Adva.

Read https://napalm.readthedocs.io for more information.
"""

import tempfile
import ipaddress
import difflib
from threading import Thread
import socket
import time
import io
import re
import logging

from napalm.base import NetworkDriver
from napalm.base.helpers import textfsm_extractor
from napalm.base.exceptions import (
    ConnectionException,
    SessionLockedException,
    MergeConfigException,
    ReplaceConfigException,
    CommandErrorException,
)

from netmiko import ConnectHandler
import tftpy

logger = logging.getLogger(__name__)
logging.getLogger("tftpy.TftpServer").setLevel(logging.ERROR)

class AdvaDriver(NetworkDriver):
    """Napalm driver for Adva."""

    def __init__(self, hostname, username, password, timeout=60, optional_args=None):
        """Constructor."""
        self.device = None
        self.hostname = hostname
        self.username = username
        self.password = password
        self.timeout = timeout
        self.port = 22

        if timeout is None:
            self.timeout = 60
        if optional_args is None:
            optional_args = {}
        self.optional_args = optional_args

        self.merge_candidate = False
        self.replace_candidate = False

    def open(self):
        """Implement the NAPALM method open (mandatory)"""

        device = {
            'device_type':"generic",
            'ip':self.hostname,
            'port':self.port,
            'username':self.username,
            'password':self.password,
            'timeout':self.timeout,
            'conn_timeout':self.timeout,
            'auth_timeout':self.timeout,
            'verbose':False,
        }
        device.update(self.optional_args)

        try:
            self.device = ConnectHandler(**device)
            self.device.session_preparation()
            self.device.send_command("", expect_string=r"-->")

        except Exception:
            raise ConnectionException(
                "Cannot connect to switch: %s:%s" % (self.hostname, self.port)
            )

    def close(self):
        """Implement the NAPALM method close (mandatory)"""
        self.device.disconnect()

    def send_command(self, command_list, expect_string=r"-->"):
        """Convenience function for self.device.send_command
        Supports a single command, or a list of commands
        """
        if type(command_list) == str:
            return self.device.send_command(command_list, expect_string=expect_string)

        command_list.append("home")
        return self.device.send_multiline(command_list, expect_string=expect_string)

    def is_alive(self):
        try:
            self.send_command("")
            return {"is_alive": True}
        except AttributeError:
            return {"is_alive": False}

    def get_facts(self):
        show_system = self.send_command("show system")
        system_info = textfsm_extractor(self, "show_system", show_system)[0]

        self.send_command("network-element ne-1", expect_string=r"NE-1-->")
        show_shelf_info = self.send_command("show shelf-info")
        self.send_command("home", expect_string=r"-->")
        serial_number = textfsm_extractor(self, "show_shelf_info", show_shelf_info)[0]

        show_ports = self.device.send_command_timing("show ports")
        interfaces = textfsm_extractor(self, "show_ports", show_ports)
        interface_list = [p["port"] for p in interfaces]

        uptime = 0
        if system_info["uptimedays"]:
            uptime += int(system_info["uptimedays"]) * 86400
        if system_info["uptimehours"]:
            uptime += int(system_info["uptimehours"]) * 3600
        if system_info["uptimeminutes"]:
            uptime += int(system_info["uptimeminutes"]) * 60
        if system_info["uptimeseconds"]:
            uptime += int(system_info["uptimeseconds"])

        return {
            "hostname": system_info["hostname"],
            "fqdn": system_info["hostname"]
            if "." in system_info["hostname"]
            else "false",
            "vendor": "Adva",
            "model": system_info["model"],
            "serial_number": serial_number["serial"],
            "interface_list": interface_list,
            "os_version": system_info["version"],
            "uptime": float(uptime),
        }

    def _get_port_speed(self, speed):
        """Convert port speed to Mbps (int) if there is one"""

        if speed == "negotiating" or speed == "none":
            return -1.0
        elif "10g" in speed:
            return 10000
        elif "25g" in speed:
            return 25000
        else:
            return float(speed.split("-")[1])

    def get_interfaces(self):
        show_ports = self.send_command("show ports")
        ports = textfsm_extractor(self, "show_ports", show_ports)
        interface_list = [p["port"] for p in ports]

        result = {}
        for i in interface_list:
            if "network" in i:
                show_network_port = self.device.send_command_timing(
                    f"show network-port {i}"
                )
                port_details = textfsm_extractor(
                    self, "show_port_details", show_network_port
                )[0]
            else:
                show_access_port = self.device.send_command_timing(
                    f"show access-port {i}"
                )
                port_details = textfsm_extractor(
                    self, "show_port_details", show_access_port
                )[0]

            result[i] = {
                "description": port_details["alias"],
                "is_enabled": port_details["adminstate"] == "in-service",
                "is_up": port_details["operationalstate"] == "normal",
                "mac_address": port_details["macaddress"],
                "mtu": int(port_details["mtu"]),
                "speed": self._get_port_speed(port_details["speed"]),
                "last_flapped": -1.0,
            }

        return result

    def get_interfaces_ip(self):
        show_run_mgmttnl = self.send_command(
            "show running-config delta partition mgmttnl"
        )
        info = textfsm_extractor(self, "show_run_mgmttnl", show_run_mgmttnl)
        result = {}
        for i in info:
            result[i["port"]] = {
                "ipv4": {
                    i["ipaddress"]: {
                        "prefix_length": ipaddress.IPv4Network(
                            f"{i['ipaddress']}/{i['subnet']}", strict=False
                        ).prefixlen
                    }
                }
            }

        return result

    def get_interfaces_vlans(self):
        show_ports = self.send_command("show ports")
        ports = textfsm_extractor(self, "show_ports", show_ports)
        interface_list = [p["port"] for p in ports]

        result = {}
        for i in interface_list:
            if "network" in i:
                mode = "trunk"
            else:
                mode = "access"

            result[i] = {
                "mode": mode,
                "access-vlan": -1,
                "trunk-vlans": [],
                "native-vlan": -1,
                "tagged-native-vlan": False,
            }

        show_flows = self.send_command("show running-config delta partition flow")
        flows = textfsm_extractor(self, "show_run_flow", show_flows)
        for flow in flows:
            show_flow = self.send_command(f"show flow {flow['flowname']}")
            flow_data = textfsm_extractor(self, "show_flow", show_flow)[0]
            if flow_data["adminstate"] == "in-service":
                result[flow_data["accessinterface"]]["access-vlan"] = flow_data["vlan"]
                result[flow_data["networkinterface"]]["trunk-vlans"].append(
                    flow_data["vlan"]
                )

        # get management vlans
        show_mgmt_tnl = self.send_command("show running-config delta partition mgmttnl")
        mgmt_flows = textfsm_extractor(self, "show_run_mgmttnl", show_mgmt_tnl)
        if mgmt_flows:
            for mgmt_flow in mgmt_flows:
                result[mgmt_flow["port"]]["trunk-vlans"].append(mgmt_flow["vlan"])

        return result

    def get_vlans(self):
        result = {}

        # get customer flow vlans
        show_flows = self.send_command("show running-config delta partition flow")
        flows = textfsm_extractor(self, "show_run_flow", show_flows)
        for flow in flows:
            show_flow = self.send_command(f"show flow {flow['flowname']}")
            flow_data = textfsm_extractor(self, "show_flow", show_flow)[0]
            if flow_data["adminstate"] == "in-service":
                result[flow_data["vlan"]] = {
                    "name": flow_data["circuitname"],
                    "interfaces": [
                        flow_data["networkinterface"],
                        flow_data["accessinterface"],
                    ],
                }

        # get management flow vlans
        show_mgmt_tnl = self.send_command("show running-config delta partition mgmttnl")
        mgmt_flows = textfsm_extractor(self, "show_run_mgmttnl", show_mgmt_tnl)
        if mgmt_flows:
            for mgmt_flow in mgmt_flows:
                result[mgmt_flow["vlan"]] = {
                    "name": mgmt_flow["circuitname"],
                    "interfaces": [mgmt_flow["port"]],
                }

        return result

    def get_lldp_neighbors(self):
        show_lldp_detail = self.send_command("show lldp detail")
        lldp_neighbours = textfsm_extractor(self, "show_lldp_detail", show_lldp_detail)

        result = {}
        for i in lldp_neighbours:
            result[i["localport"]] = [
                {"hostname": i["remotehostname"], "port": i["remoteport"]}
            ]

        return result

    def get_static_routes(self):
        show_ip_routes = self.send_command("show ip-routes")
        static_routes = textfsm_extractor(self, "show_ip_routes", show_ip_routes)

        result = []
        for i in static_routes:
            result.append(
                {
                    "prefix": ipaddress.IPv4Network(
                        f"{i['prefix']}/{i['subnet']}"
                    ).with_prefixlen,
                    "nexthop": i["nexthop"],
                    "name": None,
                    "vrf": None,
                }
            )

        return result

    def get_mac_address_table(self):
        self.send_command("network-element ne-1", expect_string=r"NE-1-->")
        self.send_command("configure nte nte", expect_string=r"NE-1:nte(.*)-1-1-1-->")

        show_ports = self.send_command("show ports")
        access_ports = textfsm_extractor(self, "show_ports_up_access", show_ports)

        mac_address_table = []
        for p in access_ports:
            self.send_command(
                f"configure access-port {p['port']}",
                expect_string=rf"-NE-1:{p['port']}",
            )
            show_flows = self.send_command("list flows")
            flows = textfsm_extractor(self, "show_port_flows", show_flows)

            for flow in flows:
                self.send_command(
                    f"configure flow {flow['flow']}",
                    expect_string=rf"NE-1:{flow['flow']}",
                )
                list_fwd = self.send_command("list fwd-entries")
                macs = textfsm_extractor(self, "list_fwd_entries", list_fwd)
                self.send_command("back", expect_string=rf"NE-1:{p['port']}")

                for mac in macs:
                    mac_address_table.append(
                        {
                            "mac": mac["mac"],
                            "interface": mac["port"],
                            "vlan": -1,
                            "static": bool(mac["type"] == "static"),
                            "active": bool(mac["status"] == "Valid"),
                            "moves": -1,
                            "last_move": -1.0,
                        }
                    )

            self.send_command("back", expect_string=rf"NE-1:nte(.*)-1-1-1-->")

        return mac_address_table

    def get_config(self, retrieve="all", sanitized=False):
        """Implementation of get_config for Adva.

        Platform does not support candidate configs, and startup and running configs are identical.
        It can storefiles which can be loaded as configs, but we ignore that here.

        """

        configs = {
            "startup": "",
            "running": "",
            "candidate": "",
        }

        if retrieve in ("running", "all"):
            command = "show running-config delta"
            output = self.send_command(command)
            configs["running"] = output

        if retrieve in ("startup", "all"):
            command = "show running-config delta"
            output = self.send_command(command)
            configs["startup"] = output

        return configs

    def compare_config(self):
        raise NotImplementedError("Config compare not supported on merge configs")

    def discard_config(self):
        self.merge_candidate = False
        self.replace_candidate = False

    def load_merge_candidate(self, filename=None, config=None):
        if filename and config:
            raise MergeConfigException("Cannot specify both filename and config")

        if filename:
            with open(filename, "r") as stream:
                self.merge_candidate = stream.read()

        if config:
            self.merge_candidate = self._clean_config(config)

        # Transfer merge candidate
        self._transfer_file(self.merge_candidate)

        # Validate merge candidate
        self._validate_candidate(self.merge_candidate)

    def load_replace_candidate(self, filename=None, config=None):
        if filename and config:
            raise ReplaceConfigException("Cannot specify both filename and config")

        if filename:
            with open(filename, "r") as stream:
                self.replace_candidate = stream.read()

        if config:
            self.replace_candidate = self._clean_config(config)

        # Transfer replace candidate
        self._transfer_file(self.replace_candidate)

        # Validate merge candidate
        self._validate_candidate(self.replace_candidate)

    def commit_config(self, message=""):
        """
        Send self.merge_candidate to running-config via tftp
        """

        if self.merge_candidate and self.replace_candidate:
            raise MergeConfigException("Both merge and replace candidate found")

        if not self.merge_candidate and not self.replace_candidate:
            raise MergeConfigException("No candidate loaded")

        if self.merge_candidate:
            result = self.send_command(["admin config", "load candidate", "home"])
            if 'ConfigFile load failed' in result:
                show_configfile_status = self.send_command("show configfile-status")
                configfile_status = textfsm_extractor(self, "show_configfile_status", show_configfile_status)
                raise MergeConfigException(configfile_status[0]['error'])
        elif self.replace_candidate:
            self.send_command(["admin config", "restart-with-configfile candidate yes"])

    def _clean_config(self, content):
        ''' Ensure config content is in the correct format:

        - In banner \\n strings need to be escaped for python
        - Config must end with a newline
        '''

        content = content.replace('\\n','\\\\n')
        if not content.endswith("\n"):
            content += "\n"
        return content

    def _transfer_file(self, filecontent, destfile='candidate'):
        # Transfer merge candidate with tftp
        with tempfile.TemporaryDirectory() as temp_dir:
            # Setup TFTP server
            tftp_server = tftpy.TftpServer(
                tftproot=temp_dir,
                dyn_file_func=self._tftp_handler(filecontent),
            )
            tftp_thread = Thread(target=tftp_server.listen)
            tftp_thread.daemon = True
            tftp_thread.start()

            self.send_command(["configure system", "tftp enabled", "home"])
            result = self.send_command(
                [
                    "admin config",
                    f"transfer-file tftp get ip-address {self._get_ipaddress()} {destfile} yes",
                    "home",
                ]
            )
            logger.info(result)

            # Server downloads in the background. Sleep to wait for it
            time.sleep(5)

            tftp_server.stop()
            tftp_thread.join()

    def _tftp_handler(self, merge_candidate):
        """tftp handler. return merge candidate no matter what is requested."""

        def _handler(fn, raddress=None, rport=None):
            if fn == "candidate":
                return io.StringIO(
                    "# DO NOT EDIT THIS LINE. FILE_TYPE=CONFIGURATION_FILE VERSION=13.1.1\n"
                    + merge_candidate
                )

        return _handler

    def _get_ipaddress(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("1.1.1.1", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip

    def _validate_candidate(self, candidate_config):
        self.send_command("admin config")

        list_configfile = self.send_command("list")
        if 'candidate' not in list_configfile:
            raise MergeConfigException(
                "Candidate config not transferred to device"
            )

        configfile_data = self.send_command("show configfile candidate")

        # Strip command output and config file header from output
        configfile_data = re.sub(
            "(?s).*?# DO NOT EDIT THIS LINE.*?\n(.*)", "\\1", configfile_data, 1
        )

        configfile_data_list = [
            line.strip() for line in configfile_data.splitlines() if line
        ]
        candidate_config_list = [
            line.strip() for line in candidate_config.splitlines() if line
        ]

        if configfile_data_list != candidate_config_list:
            diff = difflib.unified_diff(configfile_data_list, candidate_config_list)
            print("\n".join(diff))
            raise MergeConfigException(
                "Candidate config on device not the same as merge candidate"
            )
