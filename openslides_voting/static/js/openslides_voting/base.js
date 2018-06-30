(function () {

'use strict';

angular.module('OpenSlidesApp.openslides_voting', [
    'OpenSlidesApp.openslides_voting.templates',
    'OpenSlidesApp.users',
    'OpenSlidesApp.motions'
])

.factory('AuthorizedVoters', [
    'DS',
    function (DS) {
        var name = 'openslides_voting/authorized-voters';
        return DS.defineResource({
            name: name,
            methods: {
                getResourceName: function () {
                    return name;
                },
            },
            relations: {
                belongsTo: {
                    'motions/motion-poll': {
                        localField: 'motionPoll',
                        localKey: 'motion_poll_id',
                    },
                    'assignments/poll': {
                        localField: 'assignmentPoll',
                        localKey: 'assignment_poll_id',
                    },
                }
            },
        });
    }
])

.factory('VotingController', [
    'DS',
    'gettext',
    function (DS, gettext) {
        var name = 'openslides_voting/voting-controller';
        return DS.defineResource({
            name: name,
            methods: {
                getResourceName: function () {
                    return name;
                },
                getErrorMessage: function (status, text) {
                    if (status == 503) {
                        return gettext('VotingController not running!');
                    }
                    return status + ': ' + text;
                }
            },
            relations: {
                belongsTo: {
                    'openslides_voting/voting-principle': {
                        localField: 'principle',
                        localKey: 'principle_id',
                    },
                },
            },
        });
    }
])

.factory('Keypad', [
    'DS',
    'gettext',
    function (DS, gettext) {
        var name = 'openslides_voting/keypad',
            powerLevel = ['', gettext('full'), gettext('medium'), gettext('low'), gettext('empty')],
            powerCSSIcon = ['', 'full', 'half', 'quarter', 'empty'],
            powerCSSColor = ['', '', '', 'danger', 'danger'];

        return DS.defineResource({
            name: name,
            computed: {
                // No websocket update on computed!
                // active and identified are created and updated by KeypadListCtrl.
            },
            methods: {
                getResourceName: function () {
                    return name;
                },
                getTitle: function () {
                    return 'Keypad ' + this.number;
                },
                isActive: function () {
                    return this.user === undefined || this.user.is_present;
                },
                isIdentified: function () {
                    return this.user !== undefined;
                },
                power: function () {
                    return powerLevel[this.battery_level + 1];
                },
                powerCSSIcon: function () {
                    return powerCSSIcon[this.battery_level + 1];
                },
                powerCSSColor: function () {
                    return powerCSSColor[this.battery_level + 1];
                }
            },
            relations: {
                belongsTo: {
                    'users/user': {
                        localField: 'user',
                        localKey: 'user_id'
                    }
                }
            }
        });
    }
])

.factory('VotingPrinciple', [
    'DS',
    function (DS) {
        var name = 'openslides_voting/voting-principle';
        return DS.defineResource({
            name: name,
            computed: {
                // Step between two values based on precision: 1, 0.1, 0.01 etc.
                step: function () {
                    return Math.pow(10, -this.decimal_places);
                },
            },
            methods: {
                getResourceName: function () {
                    return name;
                },
                shares: function () {
                    return DS.filter('openslides_voting/voting-share', {principle_id: this.id});
                },
                share: function (delegate) {
                    var share = DS.filter('openslides_voting/voting-share', {
                        principle_id: this.id,
                        delegate_id: delegate.id,
                    });
                    return share.length ? share[0] : null;
                },
            },
            relations: {
                hasMany: {
                    'motions/motion': {
                        localField: 'motions',
                        localKeys: 'motions_id'
                    },
                    'assignments/assignment': {
                        localField: 'assignments',
                        localKeys: 'assignments_id'
                    },
                },
            },
        });
    }
])

.factory('VotingShare', [
    'DS',
    function (DS) {
        var name = 'openslides_voting/voting-share';
        return DS.defineResource({
            name: name,
            validate: function (options, share, callback) {
                var shares = parseFloat(share.shares);
                if (isNaN(shares) || shares <= 0) {
                    shares = 1;
                }
                var decimalPlaces = DS.get('openslides_voting/voting-principle', share.principle_id);
                share.shares = parseFloat(shares.toFixed(decimalPlaces));
                callback(null, share);
            },
            methods: {
                getResourceName: function () {
                    return name;
                },
            },
            relations: {
                belongsTo: {
                    'users/user': {
                        localField: 'delegate',
                        localKey: 'delegate_id'
                    },
                    'openslides_voting/voting-principle': {
                        localField: 'principle',
                        localKey: 'principle_id'
                    },
                },
            },
        });
    }
])

.factory('VotingProxy', [
    'DS',
    'User',
    function (DS, User) {
        var name = 'openslides_voting/voting-proxy';
        return DS.defineResource({
            name: name,
            relations: {
                belongsTo: {
                    'users/user': {
                        localField: 'rep',
                        localKey: 'proxy_id'
                    }
                }
            }
        });
    }
])

.factory('MotionAbsenteeVote', [
    'DS',
    'gettextCatalog',
    'User',
    'Motion',
    function (DS, gettextCatalog, User, Motion) {
        var name = 'openslides_voting/motion-absentee-vote';
        var voteOption = {
            Y: gettextCatalog.getString('Yes'),
            N: gettextCatalog.getString('No'),
            A: gettextCatalog.getString('Abstain')
        };
        var voteIcon = {
            Y: 'thumbs-up',
            N: 'thumbs-down',
            A: 'ban'
        };

        return DS.defineResource({
            name: name,
            relations: {
                belongsTo: {
                    'users/user': {
                        localField: 'delegate',
                        localKey: 'delegate_id'
                    },
                    'motions/motion': {
                        localField: 'motion',
                        localKey: 'motion_id'
                    }
                }
            },
            methods: {
                getResourceName: function () {
                    return name;
                },
                getTitle: function () {
                    return this.delegate.full_name + ', ' + this.getObjectTitle() + ', '
                        + this.getVote();
                },
                getObjectTitle: function () {
                    if (this.motion) {
                        return this.motion.getAgendaTitle();
                    }
                },
                getVote: function () {
                    return voteOption[this.vote];
                },
                getVoteIcon: function () {
                    return voteIcon[this.vote];
                },
            },
        });
    }
])

.factory('AssignmentAbsenteeVote', [
    'DS',
    'gettextCatalog',
    'User',
    'Motion',
    function (DS, gettextCatalog, User, Motion) {
        var name = 'openslides_voting/assignment-absentee-vote';
        var voteOption = {
            Y: gettextCatalog.getString('Yes'),
            N: gettextCatalog.getString('No'),
            A: gettextCatalog.getString('Abstain')
        };
        var voteIcon = {
            Y: 'thumbs-up',
            N: 'thumbs-down',
            A: 'ban'
        };

        return DS.defineResource({
            name: name,
            relations: {
                belongsTo: {
                    'users/user': {
                        localField: 'delegate',
                        localKey: 'delegate_id'
                    },
                    'assignments/assignment': {
                        localField: 'assignment',
                        localKey: 'assignment_id'
                    }
                }
            },
            methods: {
                getResourceName: function () {
                    return name;
                },
                getTitle: function () {
                    return this.delegate.full_name + ', ' + this.getObjectTitle() + ', '
                        + this.getVote();
                },
                getObjectTitle: function () {
                    if (this.assignment) {
                        return this.assignment.getAgendaTitle();
                    }
                },
                getVote: function () {
                    var intVote = parseInt(this.vote);
                    if (isNaN(intVote)) {
                        return voteOption[this.vote];
                    } else {
                        return this.vote;
                    }
                },
                getVoteIcon: function () {
                    return voteIcon[this.vote];
                },
            },
        });
    }
])

.factory('MotionPollBallot', [
    'DS',
    'gettextCatalog',
    function (DS, gettextCatalog) {
        var name = 'openslides_voting/motion-poll-ballot';
        var voteOption = {
            Y: gettextCatalog.getString('Yes'),
            N: gettextCatalog.getString('No'),
            A: gettextCatalog.getString('Abstain')
        };
        var voteIcon = {
            Y: 'thumbs-up',
            N: 'thumbs-down',
            A: 'ban'
        };

        return DS.defineResource({
            name: name,
            relations: {
                belongsTo: {
                    'users/user': {
                        localField: 'user',
                        localKey: 'delegate_id'
                    }
                }
            },
            methods: {
                getResourceName: function () {
                    return name;
                },
                getVote: function () {
                    return voteOption[this.vote];
                },
                getVoteIcon: function () {
                    return voteIcon[this.vote];
                },
            },
        });
    }
])

.factory('AssignmentPollBallot', [
    'DS',
    'gettextCatalog',
    function (DS, gettextCatalog) {
        var name = 'openslides_voting/assignment-poll-ballot';
        return DS.defineResource({
            name: name,
            relations: {
                belongsTo: {
                    'users/user': {
                        localField: 'user',
                        localKey: 'delegate_id'
                    }
                }
            },
            methods: {
                getResourceName: function () {
                    return name;
                },
            },
        });
    }
])

.factory('PollType', [
    'PollTypes', // they come form the server
    function (PollTypes) {
        return {
            getDisplayName: function (value) {
                return PollTypes[value] || 'Unknown';
            },
            // returns an array of {key: 'name', displayName: 'displayName'}
            getTypes: function (includeVoteCollector) {
                return _.chain(PollTypes)
                    .map(function (value, key) {
                        return {key: key, displayName: value};
                    })
                    .filter(function (item) {
                        var isVc = (item.key === 'votecollector' || item.key === 'votecollector_anonym');
                        return !isVc || includeVoteCollector;
                    })
                    .value();
            },
        };
    }
])

.factory('MotionPollType', [
    'DS',
    'PollType',
    function (DS, PollType) {
        var name = 'openslides_voting/motion-poll-type';
        return DS.defineResource({
            name: name,
            computed: {
                displayName: function () {
                    return PollType.getDisplayName(this.type);
                },
            },
            methods: {
                getResourceName: function () {
                    return name;
                },
            },
            relations: {
                belongsTo: {
                    'motions/motion-poll': {
                        localField: 'poll',
                        localKey: 'poll_id'
                    }
                }
            },
        });
    }
])

.factory('AssignmentPollType', [
    'DS',
    'PollType',
    function (DS, PollType) {
        var name = 'openslides_voting/assignment-poll-type';
        return DS.defineResource({
            name: name,
            computed: {
                displayName: function () {
                    return PollType.getDisplayName(this.type);
                },
            },
            methods: {
                getResourceName: function () {
                    return name;
                },
            },
            relations: {
                belongsTo: {
                    'assignments/assignment-poll': {
                        localField: 'poll',
                        localKey: 'poll_id'
                    }
                }
            },
        });
    }
])

.factory('AttendanceLog', [
    'DS',
    function (DS) {
        var name = 'openslides_voting/attendance-log';
        return DS.defineResource({
            name: name,
            methods: {
                getResourceName: function () {
                    return name;
                },
                json: function () {
                    return angular.fromJson(this.message.replace(/'/g, '"'));
                },
            }
        });
    }
])

.factory('VotingToken', [
    'DS',
    function (DS) {
        var name = 'openslides_voting/voting-token';
        return DS.defineResource({
            name: name,
            methods: {
                getResourceName: function () {
                    return name;
                },
            },
        });
    }
])

.factory('Delegate', [
    '$q',
    'User',
    'VotingPrinciple',
    'Keypad',
    'VotingProxy',
    'VotingShare',
    'Config',
    'Group',
    function ($q, User, VotingPrinciple, Keypad, VotingProxy, VotingShare, Config, Group) {
        return {
            isDelegate: function (user) {
                if (user) {
                    return _.includes(user.getPerms(), 'openslides_voting.can_vote');
                }
            },
            getDelegates: function () {
                var groups_id = [];
                _.forEach(Group.getAll(), function (group) {
                    if (_.includes(group.permissions, 'openslides_voting.can_vote')) {
                        groups_id.push(group.id);
                    }
                });
                return _.filter(User.getAll(), function (user) {
                    return _.intersection(user.groups_id, groups_id).length;
                });
            },
            getCellName: function (user) {
                var name,
                    sep = '<br/>',
                    firstName = _.trim(user.first_name),
                    lastName = _.trim(user.last_name),
                    config = Config.get('voting_delegate_board_name').value;
                if (config == 'last_name') {
                    // Trim off the first name.
                    // This applies to use cases where first name is empty and last name is 'last, first'.
                    name = lastName.split(',')[0];
                }
                else {
                    if (config == 'short_name') {
                        firstName = firstName.substr(0, 1);
                        lastName = lastName.substr(0, 3);
                        sep = ',';
                    }
                    if (lastName && firstName) {
                        name = lastName + sep + firstName;
                    }
                    else {
                        name = lastName || firstName;
                    }
                }
                return name;
            },
            getKeypad: function (userId) {
                var keypads = Keypad.filter({ user_id: userId });
                return keypads.length > 0 ? keypads[0] : null;
            },
            getProxy: function (userId) {
                var proxies = VotingProxy.filter({ delegate_id: userId });
                return proxies.length > 0 ? proxies[0] : null;
            },
            getStatus: function (item) {
                if (item.proxy !== null) {
                    return 'has_proxy';
                }
                if (item.keypad !== null && item.user.is_present) {
                    return 'can_vote';
                }
                return 'inactive';
            },
            getMandates: function (delegate) {
                return VotingProxy.filter({ proxy_id: delegate.id });
            },
            getMandatesIds: function (delegate) {
                return _.map(this.getMandates(delegate), function (proxy) {
                    return proxy.delegate_id;
                });
            },
            getShares: function (delegate) {
                var shares = {};
                _.forEach(VotingPrinciple.getAll(), function (principle) {
                    var share = principle.share(delegate);
                    if (share) {
                        shares[principle.id] = parseFloat(share.shares);
                    }
                });
                return shares;
            },
            // Returns a promise from the save or create call.
            updateKeypad: function (user, newNumber) {
                if (newNumber) {
                    if (user.keypad && user.keypad.id) {
                        // Update keypad. Must get keypad from store!
                        var keypad = Keypad.get(user.keypad.id);
                        keypad.number = newNumber;
                        return $q(function (resolve, reject) {
                            Keypad.save(keypad).then(function (success) {
                                resolve(success);
                            }, function (error) {
                                Keypad.refresh(user.keypad);
                                reject(error);
                            });
                        });
                    } else {
                        // Create item.keypad.
                        return Keypad.create({
                            user_id: user.id,
                            number: newNumber,
                        });
                    }
                } else if (user.keypad) {
                    return Keypad.destroy(user.keypad);
                }
            },
            updateProxy: function (user, proxyId) {
                if (proxyId) {
                    if (user.proxy) {
                        // Update vp. Must get vp from the store!
                        var vp = VotingProxy.get(user.proxy.id);
                        vp.proxy_id = user.proxy_id;
                        return VotingProxy.save(vp);
                    }
                    else {
                        // Create vp.
                        return VotingProxy.create({
                            delegate_id: user.id,
                            proxy_id: proxyId
                        });
                    }
                }
                else if (user.proxy) {
                    // Destroy vp.
                    return VotingProxy.destroy(user.proxy);
                }
            },
            // returns an array of promises
            updateMandates: function (user) {
                // Update mandates to user.mandates_id list.
                // Re-use existing mandates.
                var promises = [],
                    m = 0,
                    mandates = VotingProxy.filter({
                        where: {
                            delegate_id: {
                                'notIn': user.mandates_id
                            },
                            proxy_id: {
                                '==': user.id
                            }
                        }
                    });
                _.forEach(user.mandates_id, function (id) {
                    var proxies = VotingProxy.filter({ delegate_id: id });
                    if (proxies.length > 0) {
                        // Update existing foreign mandate.
                        proxies[0].proxy_id = user.id;
                        promises.push(VotingProxy.save(proxies[0]));
                    }
                    else if (m < mandates.length) {
                        // Update existing mandate.
                        var proxy = mandates[m++];
                        proxy.delegate_id = id;
                        proxy.proxy_id = user.id;
                        promises.push(VotingProxy.save(proxy));
                    }
                    else {
                        // Create new mandate.
                        promises.push(VotingProxy.create({
                            delegate_id: id,
                            proxy_id: user.id
                        }));
                    }
                    // Destroy keypad of mandate.
                    var keypads = Keypad.filter({user_id: id});
                    if (keypads.length > 0) {
                        promises.push(Keypad.destroy(keypads[0]));
                    }
                    // Set mandate not present.
                    var mandate = User.get(id);
                    if (mandate.is_present) {
                        mandate.is_present = false;
                        promises.push(User.save(mandate));
                    }
                });

                // Delete left-over mandates.
                for (; m < mandates.length; m++) {
                    promises.push(VotingProxy.destroy(mandates[m].id));
                }

                return promises;
            },
            // returns a list of promises
            updateShares: function (delegate) {
                var self = this;
                return _.filter(_.map(delegate.shares, function (value, principleId) {
                    var shares = VotingShare.filter({
                        delegate_id: delegate.id,
                        principle_id: principleId,
                    });
                    var share = shares.length == 1 ? shares[0]: null;
                    return self.updateShare(delegate, share, value, principleId);
                }));
            },
            updateShare: function (delegate, share, newValue, principleId) {
                if (newValue) {
                    if (share) {
                        // Update VotingShare.
                        share.shares = newValue;
                        return VotingShare.save(share);
                    } else {
                        // Create VotingShare.
                        return VotingShare.create({
                            delegate_id: delegate.id,
                            principle_id: principleId,
                            shares: newValue
                        });
                    }
                } else if (share) {
                    // Destroy VotingShare.
                    return VotingShare.destroy(share);
                }
            },
        };
    }
])

.config([
    'OpenSlidesPluginsProvider',
    function(OpenSlidesPluginsProvider) {
        OpenSlidesPluginsProvider.registerPlugin({
            name: 'openslides_voting',
            display_name: 'Voting',
            languages: ['de']
        });
    }
])

.run([
    'AssignmentAbsenteeVote',
    'AssignmentPollBallot',
    'AssignmentPollType',
    'AttendanceLog',
    'AuthorizedVoters',
    'Delegate',
    'Keypad',
    'MotionAbsenteeVote',
    'MotionPollBallot',
    'MotionPollType',
    'VotingPrinciple',
    'VotingProxy',
    'VotingShare',
    'VotingToken',
    'VotingController',
    function (AssignmentAbsenteeVote, AssignmentPollBallot, AssignmentPollType,
        AuthorizedVoters, Delegate, Keypad, MotionAbsenteeVote, MotionPollBallot,
        MotionPollType, VotingPrinciple, VotingProxy, VotingShare, VotingToken,
        VotingController) {}
])

.run([
    '$rootScope',
    '$http',
    function ($rootScope, $http) {
        $rootScope.stopAnyVoting = function () {
            $http.post('/rest/openslides_voting/voting-controller/1/stop/').then(function (s) {
                console.log('success', s);
            }, function (e) {
                console.log('error', e);
            });
        };
    }
]);

}());

// DEBUGGING: If something went wrong, and an active voting has to be stopped.
// This may happen, if you delete a poll, with a current voting.
function stopAnyVoting () {
    angular.element(document.body).scope().$root.stopAnyVoting();
}
