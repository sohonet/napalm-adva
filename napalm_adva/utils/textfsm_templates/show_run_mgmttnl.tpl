Value Port (\S+)
Value IPAddress (\S+)
Value Subnet (\S+)
Value VLAN (\d{0,4})
Value CircuitName (\S+)

Start
  ^\s*add mgmttunnel\s\d\s"${CircuitName}"\s${Port}.*\D+\s${VLAN}\s\D+.*\s${IPAddress}\s${Subnet}