# /bin/bash
#
# When the IP address changes, these are the changes that we need to make.
#
# The comments in the freeswitch vars.xml suggest that we can use stun, but my experience suggests that
# we can't, and have to hard-wire the external IP address in vars.xml
#
# nginx can't connect to freeswitch on the loopback address, or the outbound SIP advertisements will
# use private IP address, so we have to connect to the external IP address.
#
# And, of course, we need a loopback address for the external IP address, to connect to it at all.

set_ip() {
    if [ ! -z "$IP" ]; then
	# Can't use xmlstarlet's --inplace option because we need to "unesc"ape &gt; in bong-ring,
	# though I doubt that we use bong-ring at all
	cat /opt/freeswitch/etc/freeswitch/vars.xml \
	    | xmlstarlet ed -O -P -u './/X-PRE-PROCESS[starts-with(@data, "external_rtp_ip")]/@data' -v "external_rtp_ip=$IP" \
	    | xmlstarlet ed -O -P -u './/X-PRE-PROCESS[starts-with(@data, "external_sip_ip")]/@data' -v "external_sip_ip=$IP" \
	    | xmlstarlet -q unesc > /tmp/vars.xml
	cp /tmp/vars.xml /opt/freeswitch/etc/freeswitch/vars.xml

	sed -i "s|proxy_pass .*:7443;|proxy_pass https://$IP:7443;|" /etc/bigbluebutton/nginx/sip.nginx
	ip addr add $IP dev lo
    fi
}

IP=$(pystun | grep IP | cut -d ' ' -f 3)

set_ip
service freeswitch restart
service nginx restart
