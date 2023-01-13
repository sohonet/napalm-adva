Value LocalPort (\w*-\d-\d-\d-\d)
Value RemoteChassisID (\S+)
Value RemoteHostname (\S+)
Value RemotePort (\S+)
Value RemoteDescription (\S+)
Value RemoteMacAddress (\S+)

Start
  ^\s*Local Port Eid : ${LocalPort}
  ^\s*Destination MAC : ${RemoteMacAddress}
  ^\s*Chassis ID : ${RemoteChassisID}
  ^\s*Port ID : ${RemotePort}
  ^\s*Port Description : ${RemoteDescription}
  ^\s*System Name : ${RemoteHostname} -> Record