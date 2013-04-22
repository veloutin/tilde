from twisted.application.service import ServiceMaker

tilde = ServiceMaker(
    'tilde', 'tilde.tap', 'Run the tilde service', 'tilde')
