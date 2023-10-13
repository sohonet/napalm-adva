# napalm-adva

Napalm Driver for Adva CPEs

## WARNING ##

When committing a replace_candidate, the device will be rebooted to load the config!

## Supported Functions
* get_facts
* get_interfaces
* get_intefaces_vlans
* get_vlans
* get_lldp_neighbors
* get_static_routes
* get_mac_address_table
* get_config
* load_merge_candidate
* load_replace_candidate
* discard_config
* commit_config

## Supported Devices
* Adva FSP 150-GE104
* Adva FSP 150-XG108
