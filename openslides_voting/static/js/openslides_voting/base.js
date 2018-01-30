(function () {

'use strict';

angular.module('OpenSlidesApp.openslides_voting', [
    'OpenSlidesApp.users',
    'OpenSlidesApp.motions'
])

.factory('VoteCollector', [
    'DS',
    'gettext',
    function (DS, gettext) {
        return DS.defineResource({
            name: 'openslides_voting/vote-collector',
            methods: {
                getErrorMessage: function (status, text) {
                    if (status == 503) {
                        return gettext('VoteCollector not running!');
                    }
                    return status + ': ' + text;
                }
            }
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
                getTitle: function () {
                    return "Keypad " + this.number;
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
                    return powerCSSIcon[this.battery_level + 1]
                },
                powerCSSColor: function () {
                    return powerCSSColor[this.battery_level + 1]
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
    'Category',
    function (Category) {
        return {
            getName: function (value) {
                // voting principle format: 'name.precision'.
                var name = typeof value == 'number' ? Category.get(value).name : value,
                    i = name.lastIndexOf('.');
                if (i >= 0) {
                    return name.substr(0, i);
                }
                return name;
            },
            getPrecision: function (value) {
                // voting principle format: 'name.precision'. Max. precision is 6.
                var name = typeof value == 'number' ? Category.get(value).name : value,
                    i = name.lastIndexOf('.');
                if (i >= 0) {
                    var precision = parseInt(name.substr(i + 1));
                    if (!isNaN(precision) && precision > 0) {
                        return Math.min(6, precision);
                    }
                }
                return 0;
            },
            getStep: function (value) {
                // Step between two values based on precision: 1, 0.1, 0.01 etc.
                var precision = this.getPrecision(value);
                return Math.pow(10, -precision);
            }
        };
    }
])

.factory('VotingShare', [
    'DS',
    'User',
    'Category',
    function (DS, User, Category) {
        return DS.defineResource({
            name: 'openslides_voting/voting-share',
            relations: {
                belongsTo: {
                    'users/user': {
                        localField: 'user',
                        localKey: 'delegate_id'
                    },
                    'motions/category': {
                        localField: 'category',
                        localKey: 'category_id'
                    }
                }
            }
        });
    }
])

.factory('VotingProxy', [
    'DS',
    'User',
    function (DS, User) {
        return DS.defineResource({
            name: 'openslides_voting/voting-proxy',
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

.factory('AbsenteeVote', [
    'DS',
    'gettextCatalog',
    'User',
    'Motion',
    function (DS, gettextCatalog, User, Motion) {
        var voteOption = {
            Y: gettextCatalog.getString('Yes'),
            N: gettextCatalog.getString('No'),
            A: gettextCatalog.getString('Abstain')
        },
            voteIcon = {
            Y: "thumbs-up",
            N: 'thumbs-down',
            A: 'ban'
        };

        return DS.defineResource({
            name: 'openslides_voting/absentee-vote',
            relations: {
                belongsTo: {
                    'users/user': {
                        localField: 'user',
                        localKey: 'delegate_id'
                    },
                    'motions/motion': {
                        localField: 'motion',
                        localKey: 'motion_id'
                    }
                }
            },
            methods: {
                getTitle: function () {
                    return this.user.full_name + ", " + this.getMotionTitle() + ", " + this.getVote();
                },
                getMotionTitle: function () {
                    return this.motion !== undefined ?
                        this.motion.identifier + " - " + this.motion.getTitle() : null;
                },
                getVote: function () {
                    return voteOption[this.vote];
                },
                getVoteIcon: function () {
                    return voteIcon[this.vote];
                }
            }
        });
    }
])

.factory('MotionPollBallot', [
    'DS',
    'gettextCatalog',
    'User',
    function (DS, gettextCatalog, User) {
        var voteOption = {
            Y: gettextCatalog.getString('Yes'),
            N: gettextCatalog.getString('No'),
            A: gettextCatalog.getString('Abstain')
        },
            voteIcon = {
            Y: "thumbs-up",
            N: 'thumbs-down',
            A: 'ban'
        };

        return DS.defineResource({
            name: 'openslides_voting/motion-poll-ballot',
            relations: {
                belongsTo: {
                    'users/user': {
                        localField: 'user',
                        localKey: 'delegate_id'
                    }
                }
            },
            methods: {
                getVote: function () {
                    return voteOption[this.vote];
                },
                getVoteIcon: function () {
                    return voteIcon[this.vote];
                }
            }
        });
    }
])

.factory('Delegate', [
    'User',
    'Category',
    'VotingPrinciple',
    'Keypad',
    'VotingProxy',
    'VotingShare',
    'Config',
    function (User, Category, VotingPrinciple, Keypad, VotingProxy, VotingShare, Config) {
        return {
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
            getKeypad: function (id) {
                var kps = Keypad.filter({ user_id: id });
                return kps.length > 0 ? kps[0] : null;
            },
            getProxy: function (id) {
                var vps = VotingProxy.filter({ delegate_id: id });
                return vps.length > 0 ? vps[0] : null;
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
            getMandates: function (id) {
                return VotingProxy.filter({ proxy_id: id })
            },
            getShares: function (id) {
                var shares = {};
                _.forEach(Category.getAll(), function (cat) {
                    var vss = VotingShare.filter({delegate_id: id, category_id: cat.id});
                    // Use cat.id as key.
                    shares[cat.id] = vss.length == 1 ? parseFloat(vss[0].shares) : null;
                });
                return shares;
            },
            updateKeypad: function (item, newNumber, promises, onFailed) {
                if (newNumber) {
                    if (item.keypad) {
                        // Update keypad. Must get keypad from store!
                        var kp = Keypad.get(item.keypad.id);
                        kp.number = newNumber;
                        promises.push(Keypad.save(kp).then(null, function (error) {
                            onFailed(error);
                            Keypad.refresh(item.keypad);
                        }));
                    }
                    else {
                        // Create item.keypad.
                        promises.push(Keypad.create({
                            user_id: item.user.id,
                            number: newNumber
                        }).then(null, onFailed));
                    }
                }
                else if (item.keypad) {
                    // Destroy item.keypad.
                    promises.push(Keypad.destroy(item.keypad));
                }
            },
            updateProxy: function (item, userId, promises) {
                if (userId) {
                    if (item.proxy) {
                        // Update vp. Must get vp from the store!
                        var vp = VotingProxy.get(item.proxy.id);
                        vp.proxy_id = item.proxy_id;
                        promises.push(VotingProxy.save(vp));
                    }
                    else {
                        // Create vp.
                        promises.push(VotingProxy.create({
                            delegate_id: item.user.id,
                            proxy_id: userId
                        }));
                    }
                }
                else if (item.proxy) {
                    // Destroy vp.
                    promises.push(VotingProxy.destroy(item.proxy));
                }
            },
            updateMandates: function (item, promises) {
                // Update mandates to item.mandates_id list.
                // Re-use existing mandates.
                var m = 0,
                    mandates = VotingProxy.filter({
                    where: {
                        delegate_id: {
                            'notIn': item.mandates_id
                        },
                        proxy_id: {
                            '==': item.user.id
                        }
                    }
                });
                _.forEach(item.mandates_id, function (id) {
                    var vps = VotingProxy.filter({ delegate_id: id });
                    if (vps.length > 0) {
                        // Update existing foreign mandate.
                        vps[0].proxy_id = item.user.id;
                        promises.push(VotingProxy.save(vps[0]));
                    }
                    else if (m < mandates.length) {
                        // Update existing mandate.
                        var vp = mandates[m++];
                        vp.delegate_id = id;
                        vp.proxy_id = item.user.id;
                        promises.push(VotingProxy.save(vp));
                    }
                    else {
                        // Create new mandate.
                        promises.push(VotingProxy.create({
                            delegate_id: id,
                            proxy_id: item.user.id
                        }));
                    }
                    // Destroy keypad of mandate.
                    var kps = Keypad.filter({user_id: id});
                    if (kps.length > 0) {
                        promises.push(Keypad.destroy(kps[0]));
                    }
                    // Set mandate not present.
                    var user = User.get(id);
                    if (user.is_present) {
                        user.is_present = false;
                        promises.push(User.save(user));
                    }
                });

                // Delete left-over mandates.
                for (; m < mandates.length; m++) {
                    promises.push(VotingProxy.destroy(mandates[m].id));
                }
            },
            updateShares: function (item, promises) {
                _.forEach(item.shares, function (value, key) {
                    var vss = VotingShare.filter({
                        delegate_id: item.user.id,
                        category_id: key
                    });
                    var vs = vss.length == 1 ? vss[0]: null;
                    if (value) {
                        if (vs) {
                            // Update vs.
                            vs.shares = value;
                            promises.push(VotingShare.save(vs));
                        }
                        else {
                            // Create vs.
                            promises.push(VotingShare.create({
                                delegate_id: item.user.id,
                                category_id: key,
                                shares: value
                            }));
                        }
                    }
                    else if (vs) {
                        // Destroy vs.
                        promises.push(VotingShare.destroy(vs));
                    }
                });
            }
        }
    }
])

.factory('AttendanceLog', [
    'DS',
    function (DS) {
        return DS.defineResource({
            name: 'openslides_voting/attendance-log',
            methods: {
                json: function () {
                    return angular.fromJson(this.message.replace(/'/g, '"'));
                }
            }
        });
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
    'VoteCollector',
    'Keypad',
    'VotingShare',
    'VotingProxy',
    'AbsenteeVote',
    'MotionPollBallot',
    'Delegate',
    'AttendanceLog',
    function (VoteCollector, Keypad, VotingShare, VotingProxy, AbsenteeVote, MotionPollBallot, Delegate, AttendanceLog) {}
])

}());
