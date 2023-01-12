Value AdminState (\S+)
Value CircuitName (\S+)
Value VLAN (\d+)
Value NetworkInterface (\S+)
Value AccessInterface (\S+)

Start
  ^\s*Admin State : ${AdminState}
  ^\s*Circuit Name : ${CircuitName}
  ^\s*C-Tag : ${VLAN}
  ^\s*Network Interface : ${NetworkInterface}
  ^\s*Access Interface : ${AccessInterface}