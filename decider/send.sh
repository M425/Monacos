obj=$1
whoami=$2
curl -d @sample_alarm_${obj}.json compute0${whoami}-man:4250${whoami}/overload -H "Content-type:application/json"
