"""
NML -> XML converter

Author: Henrik Thostrup Jensen <htj@nordu.net>

Copyright: NORDUnet (2013)
"""

from twisted.python import log

from xml.etree import ElementTree as ET

from opennsa import constants as cnt, nsa
from opennsa.topology import nml



LOG_SYSTEM = 'topology.nmlxml'


NML_NS = 'http://schemas.ogf.org/nml/2013/05/base#'

ET.register_namespace('nml', NML_NS)

ID = 'id'
VERSION = 'version'
TYPE = 'type'
LABEL_TYPE = 'labeltype'

NML_TOPOLOGY            = ET.QName('{%s}Topology'   % NML_NS)
NML_PORT                = ET.QName('{%s}Port'       % NML_NS)
NML_PORTGROUP           = ET.QName('{%s}PortGroup'  % NML_NS)
NML_LABEL               = ET.QName('{%s}Label'      % NML_NS)
NML_LABELGROUP          = ET.QName('{%s}LabelGroup' % NML_NS)
NML_NAME                = ET.QName('{%s}name'       % NML_NS)
NML_RELATION            = ET.QName('{%s}Relation'   % NML_NS)
NML_NODE                = ET.QName('{%s}Node'       % NML_NS)
NML_BIDIRECTIONALPORT   = ET.QName('{%s}BidirectionalPort'  % NML_NS)

# this is odd xml
NML_HASINBOUNDPORT      = NML_NS + 'hasInboundPort'
NML_HASOUTBOUNDPORT     = NML_NS + 'hasOutboundPort'
NML_MANAGEDBY           = NML_NS + 'managedBy'
NML_ISALIAS             = NML_NS + 'isAlias'



def topologyXML(network):
    # creates nml:Topology object from an nml network

    BASE_URN = cnt.URN_OGF_PREFIX + network.id_

    topology_id = cnt.URN_OGF_PREFIX + network.id_
    nml_topology = ET.Element(NML_TOPOLOGY, {ID: topology_id } )

    ET.SubElement(nml_topology, NML_NAME).text = network.name

    portName = lambda port : BASE_URN + ':' + port.name

    def addPort(nml_port_relation, port):
        nml_port = ET.SubElement(nml_port_relation, NML_PORTGROUP, {ID: portName(port)} )
        label = port.label()
        if label:
            ln = ET.SubElement(nml_port, NML_LABELGROUP, { LABEL_TYPE : label.type_} )
            ln.text = label.labelValue()
        if port.remote_port is not None:
            rpa = ET.SubElement(nml_port, NML_RELATION, { TYPE : NML_ISALIAS} )
            ET.SubElement(rpa, NML_PORTGROUP, { ID : cnt.URN_OGF_PREFIX + port.remote_port})

    for port in network.bidirectional_ports:
        pn = ET.SubElement(nml_topology, NML_BIDIRECTIONALPORT, { ID: portName(port) } )
        ET.SubElement(pn, NML_NAME).text = port.name
        ET.SubElement(pn, NML_PORTGROUP, {ID: BASE_URN + ':' + port.inbound_port.name} )
        ET.SubElement(pn, NML_PORTGROUP, {ID: BASE_URN + ':' + port.outbound_port.name} )

    if network.inbound_ports:
        nml_inbound_ports = ET.SubElement(nml_topology, NML_RELATION, {TYPE: NML_HASINBOUNDPORT})
        for port in network.inbound_ports:
            addPort(nml_inbound_ports, port)

    if network.outbound_ports:
        nml_outbound_ports = ET.SubElement(nml_topology, NML_RELATION, {TYPE: NML_HASOUTBOUNDPORT})
        for port in network.outbound_ports:
            addPort(nml_outbound_ports, port)

    return nml_topology



# xml parsing from here


def _baseName(urn_id):
    assert urn_id.startswith(cnt.URN_OGF_PREFIX), 'Identifier %s must start with urn ogf network prefix' % urn_id
    base_name = urn_id[len(cnt.URN_OGF_PREFIX):]
    return base_name


def parseNMLPort(nml_port):

    assert nml_port.tag in (NML_PORT,NML_PORTGROUP), 'Port tag name must be nml:Port or nml:PortGroup, not (%s)' % nml_port.tag
    port_id = _baseName( nml_port.attrib[ID] )

    port_name   = None
    label       = None
    remote_port = None

    for pe in nml_port:
        if pe.tag == NML_NAME:
            port_name = pe.text

        elif pe.tag in (NML_LABEL, NML_LABELGROUP):
            label_type = pe.attrib[LABEL_TYPE]
            label_value = pe.text
            label = nsa.Label(label_type, label_value)

        elif pe.tag == NML_RELATION:
            if pe.attrib[TYPE] == NML_ISALIAS:
                port_alias = pe[0].attrib[ID]
                remote_port = _baseName(port_alias)
            else:
                log.msg('Unknown nml relation type %s, ignoring' % pe.attrib[TYPE], system=LOG_SYSTEM)
        else:
            log.msg('Unknown port element %s, ignoring' % pe, system=LOG_SYSTEM)

    # make up a name if none is specified
    if port_name is None:
        port_name = port_id.split(':')[-1]

    port = nml.Port(port_id, port_name, label, remote_port)
    return port



def parseNMLTopology(nml_topology):

    assert nml_topology.tag == NML_TOPOLOGY, 'Top level container must be nml:Topology'

    topology_id = _baseName( nml_topology.attrib[ID] )

    network_name = None
    inbound_ports   = {}
    outbound_ports  = {}
    bd_ports        = [] # temporary construction

    for nte in nml_topology:
        if nte.tag == NML_NAME:
            network_name = nte.text

        elif nte.tag == NML_RELATION and nte.attrib[TYPE] == NML_HASINBOUNDPORT:
            for npe in nte:
                if not npe.tag in (NML_PORT, NML_PORTGROUP):
                    log.msg('Relation with inboundPort type has non-Port element (%s), ignoring' % npe.tag, system=LOG_SYSTEM)
                    continue
                port = parseNMLPort(npe)
                inbound_ports[port.id_] = port

        elif nte.tag == NML_RELATION and nte.attrib[TYPE] == NML_HASOUTBOUNDPORT:
            for npe in nte:
                if not npe.tag in (NML_PORT, NML_PORTGROUP):
                    log.msg('Relation with outboundPort type has non-Port element (%s), ignoring' % npe.tag, system=LOG_SYSTEM)
                    continue
                port = parseNMLPort(npe)
                outbound_ports[port.id_] = port

        elif nte.tag == NML_BIDIRECTIONALPORT:
            port_id = _baseName( nte.attrib[ID] )
            name = None
            sub_ports = []
            for pel in nte:
                if pel.tag == NML_NAME:
                    name = pel.text
                elif pel.tag in (NML_PORT, NML_PORTGROUP):
                    sub_ports.append( _baseName( pel.attrib[ID] ) )
            assert len(sub_ports) == 2, 'The number of ports in a bidirectional port must be 2'
            bd_ports.append( (port_id, name, sub_ports) )

        else:
            log.msg('Unknown topology element %s, ignoring' % nte.tag, system=LOG_SYSTEM)

    # construct the bidirectional ports
    bidirectional_ports = []

    for port_id, name, (p1, p2) in bd_ports:
        if p1 in inbound_ports:
            in_port  = inbound_ports[p1]
            out_port = outbound_ports[p2]
        else:
            in_port  = inbound_ports[p2]
            out_port = outbound_ports[p1]
        bidirectional_ports.append( nml.BidirectionalPort(port_id, name, in_port, out_port) )

    network = nml.Network(topology_id, network_name, inbound_ports.values(), outbound_ports.values(), bidirectional_ports)
    return network



def parseNSIService(nsi_service):

    assert nsi_service.tag == NSI_SERVICE, 'Top level container must be nsi:Service (is %s) ' % nsi_service.tag

    service_id = _baseName( nsi_service.attrib[ID] )
    service_type = nsi_service.findtext( str(NSI_TYPE) )

    if service_type == cnt.CS2_SERVICE_TYPE:
        endpoint = nsi_service.findtext( str(NSI_LINK) )
        nsi_agent = nsa.NetworkServiceAgent(service_id, endpoint, service_type)
        return nsi_agent
    else:
        print 'Unrecognized service type: %s' % service_type



def parseTopologyReachability(gns_topo_reach):

    vectors = {}

    assert gns_topo_reach.tag == GNS_TOPOLOGY_REACHABILITY, 'Element must be gns:TopologyReachability, not %s' % gns_topo_reach.tag

    for nml_topo in gns_topo_reach:
        assert nml_topo.tag == NML_TOPOLOGY, 'Reachablity sub-element must be nml:Topology, not %s' % nml_topo.tag
        topology_id = _baseName( nml_topo.attrib[ID] )
        cost = nml_topo.attrib[GNS_COST]
        vectors[topology_id] = int(cost)

    return vectors



def parseNSITopology(nsi_topology_source):

    tree = ET.parse(nsi_topology_source)

    nsi_nsa = tree.getroot()
    assert nsi_nsa.tag == NSI_NSA, 'Top level container must be a nsi:NSA tag'

    nsa_id  = _baseName( nsi_nsa.attrib[ID] )
    # version = nsi_nsa.attrib[VERSION] # currently not used for anything

    nsi_agent = None
    topologies = []
    vectors = {}

    for ele in nsi_nsa:

        if ele.tag == NSI_SERVICE:
            # we only support nsi agent service type for now
            if nsi_agent is not None:
                raise ValueError('NSA description listed more than one CS service')
            nsi_agent = parseNSIService(ele)

        elif ele.tag == NML_TOPOLOGY:
            topologies.append( parseNMLTopology(ele))

        elif ele.tag == GNS_TOPOLOGY_REACHABILITY:
            vectors = parseTopologyReachability(ele)

    if nsi_agent is None:
        raise ValueError('NSA description does not specify an NSI agent')
    if len(topologies) == 0:
        # there can be pure aggregaters where this is not a real error....
        raise ValueError('NSA description does not specify an NML topology')

    return nsa_id, nsi_agent, topologies, vectors

