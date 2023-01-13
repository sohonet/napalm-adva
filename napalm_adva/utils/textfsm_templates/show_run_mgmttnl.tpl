Value Port (\S+)
Value IPAddress (\S+)
Value Subnet (\S+)

Start
  ^\s*add mgmttunnel\s\d\s\S+\s${Port}.*\s${IPAddress}\s${Subnet} -> Record