from twisted.application.service import ServiceMaker

finger = ServiceMaker(
    'tilde', 'tilde.tap', 'Run the tilde service', 'tilde')
