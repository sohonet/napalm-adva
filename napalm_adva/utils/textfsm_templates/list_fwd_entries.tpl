Value Mac (\S{2}:\S{2}:\S{2}:\S{2}:\S{2}:\S{2})
Value Port (\S+)
Value Type (\S+)
Value Status (\S+)

Start
  ^\|${Mac}\s*\|.*\|${Port}\s*\|${Type}\s*\|${Status}\s*\|.* -> Record