Value Hostname (\S+)
Value Model (.+)
Value Version (\S+)
Value UptimeDays (\d+)
Value UptimeHours (\d+)
Value UptimeMinutes (\d+)
Value UptimeSeconds (\d+)

Start
  ^\s*System Name : ${Hostname}
  ^\s*System Description : ${Model}
  ^\s*Release Version : ${Version}
  ^\s*System Up Time : (${UptimeDays} days)?\s*(${UptimeHours} hrs)?\s*(${UptimeMinutes} mins)?\s*(${UptimeSeconds} secs)?