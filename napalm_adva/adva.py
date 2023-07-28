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
import ipaddress

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

    def open(self):
        """Implement the NAPALM method open (mandatory)"""

        try:
            self.device = ConnectHandler(
                device_type="generic",
                ip=self.hostname,  # saves device parameters
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=self.timeout,
                conn_timeout=self.timeout,
                verbose=False,
            )
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
