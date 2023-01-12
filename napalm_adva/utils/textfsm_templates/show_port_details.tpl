Value AdminState (\S+)
Value OperationalState (\S+)
Value Alias (\S+)
Value MacAddress (\S+)
Value MTU (\d+)
Value Speed (\S+)

Start
  ^\s*Admin State : ${AdminState}
  ^\s*Operational State : ${OperationalState}
  ^\s*Alias : ${Alias}
  ^\s*MAC Address : ${MacAddress}
  ^\s*MTU \(bytes\) : ${MTU}
  ^\s*Negotiated Port Speed : ${Speed}