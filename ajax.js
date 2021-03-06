var request = false;
var basedir = '/staff/resched-dev/';
var baseuri = basedir + 'dynamic-info.cgi';
try {
  request = new XMLHttpRequest();
} catch (trymicrosoft) {
  try {
    request = new ActiveXObject("Msxml2.XMLHTTP");
  } catch (othermicrosoft) {
    try {
      request = new ActiveXObject("Microsoft.XMLHTTP");
    } catch (failed) {
      request = false;
    }
  }
}

function cbvistoggle(cbid, visid) {
    var cbelt  = document.getElementById(cbid);
    var viselt = document.getElementById(visid);
    if (cbelt.checked) {
        viselt.style.visibility = "visible";
    } else {
        viselt.style.visibility = "hidden";
    }
}

function toggledisplay(eltid, expansionmarker, coerce) {
  var elt = document.getElementById(eltid);
  if ((coerce=='expand') || (coerce=='inline')) {
    elt.style.display = 'inline';
  } else {
    if (coerce=='block') {
      elt.style.display = 'block';
    } else {
      if (elt.style.display == 'none') {
        elt.style.display = 'inline';
      } else {
        elt.style.display = 'none';
      }
    }
  }
  if (expansionmarker) {
    var expansionelt = document.getElementById(expansionmarker);
    if (elt.style.display == "none") {
      expansionelt.firstChild.data = '+';
    } else {
      expansionelt.firstChild.data = '-';
    }
  }
}

function handleResponse() {
  if (request.readyState==4) {
    var resultdom = request.responseXML.documentElement;
    var alerts = resultdom.getElementsByTagName("alert");
    var i;
    if (alerts && alerts[0]) {
      var alerttext = alerts[0].firstChild.data;
      alert(alerttext);
    }
    var updc = resultdom.getElementsByTagName("updatecount");
    if (updc && updc[0]) {
      retrieveupdates();
    }
    var repl = resultdom.getElementsByTagName("replace");
    if (repl  && repl[0]) {
      var containerid = resultdom.getElementsByTagName("replace_within")[0].firstChild.data;
      var container   = document.getElementById(containerid);
      var replcontent = resultdom.getElementsByTagName("replacement")[0].firstChild;
      var oldnode     = container.childNodes;
      var numnodes    = oldnode.length;
      for (i=numnodes-1; i >= 0; i--) {
        container.removeChild(oldnode[i]);
      }
      container.appendChild(replcontent);
    }
    var togd = resultdom.getElementsByTagName("toggledisplay");
    if (togd) {
      for (i = 0; i < togd.length; i++) {
        var markerid = null;
        var togelt = togd[i].getElementsByTagName("toggleelement")[0].firstChild.data;
        var marker = togd[i].getElementsByTagName("togglemarker");
        var coerce = togd[i].getElementsByTagName("togglecoerce");
        if (marker && marker[0]) {
          markerid = marker[0].firstChild.data;
        }
        if (coerce && coerce[0]) {
          var vis = coerce[0].firstChild.data;
          toggledisplay(togelt, markerid, vis);
        } else {
          toggledisplay(togelt, markerid);
        }
      }
    }
    var updv = resultdom.getElementsByTagName("varupdate");
    if (updv && updv[0]) {
      var varid = resultdom.getElementsByTagName("variable")[0].firstChild.data;
      var varnv = resultdom.getElementsByTagName("newvalue")[0].firstChild.data;
      var varel = document.getElementById(varid);
      varel.value = varnv;
    }
    var foc = resultdom.getElementsByTagName("focus");
    if (foc && foc[0]) {
      var focid = foc[0].firstChild.data;
      var focel = document.getElementById(focid);
      focel.focus();
    }
  }
}

function sendajaxrequest(myargs, alternate) {
  var uri = baseuri + '?' + myargs;
  if (alternate) {
    uri = basedir + alternate + '?' + myargs;
  }
  request.open("GET", uri, true);
  request.onreadystatechange=handleResponse;
  request.send(null);
}
function onemoment(containerid) {
  var container = document.getElementById(containerid);
  insert_before_element('One Moment...', container.firstChild);
}
  
function insert_before_element(what, where) {
  // This function is black, cargo-cult magic of the worst kind.
  // But it works, at least in Gecko.  It came from the Open Clip
  // Art Library's old svg upload tool, which used it to let clip-art
  // authors add an arbitrary number of keywords.  The OCAL got the
  // jist of it from http://developer.osdl.org/bryce/js_test/test_7.html
  var range = where.ownerDocument.createRange(); // I have no clue what this does,
  range.setStartBefore(where);                   // much less this, or why it's necessary.
  where.parentNode.insertBefore(range.createContextualFragment(what),where);
  }

function augmentprogramsignupform(waitbox) {
  toggledisplay('addmoresignupsbutton', null, 'none');
  toggledisplay('onemomentnotice', null, 'inline');
  var varelt   = document.getElementById('numofnewsignups');
  var num      = varelt.value;
  num          = num - 0;
  var slimelt  = document.getElementById('signuplimit');
  var slimit;
  if (slimelt) {
    slimit   = slimelt.value - 0;
  } else {
    slimit   = num + 1;
  }
  if (num < slimit) {
    num = num + 1;
    var numerate = '<td>?</td>';
    var attender = '<td><input type="text" id="signup' + num + 'attender" name="signup' + num + 'attender" size="30" /></td>';
    var phonenum = '<td><input type="text" id="signup' + num + 'phone"    name="signup' + num + 'phone"    size="15" /></td>';
    var waitcbid = 'signup' + num + 'flagW';
    var chkboxes = '<td>'
          + ((waitbox > 0) ? ('<input type="checkbox" id="' + waitcbid + '" name="' + waitcbid + '" />&nbsp;<label for="' + waitcbid + '"><abbr title="Place on the waiting list">Wait</abbr></label>') : '')
          + '</td>';
    var comments = '<td><textarea id="signup' + num + 'comments" name="signup' + num + 'comments" rows="3" cols="25"></textarea></td>';
    var tablerow = '<tr>' + numerate + attender + phonenum + chkboxes + comments + '</tr>';
    var location = document.getElementById('insertemptysignupshere');
    insert_before_element(tablerow, location);
    varelt.value = num;
    toggledisplay('onemomentnotice', null, 'none');
    toggledisplay('addmoresignupsbutton', null, 'inline');
    var focelt = document.getElementById('signup' + num + 'attender');
    focelt.focus();
  } else {
    var elt = document.getElementById('onemomentnotice');
    insert_before_element('This program is full.', elt);
    toggledisplay('onemomentnotice', null, 'none');
  }
}

function changerecurform() {
  var selectelt      = document.getElementById('recurformselect');
  var recurstyleselt = document.getElementById('recurstyles');
  var recurlistelt   = document.getElementById('recurlist');
  if (selectelt.value == 'listed') {
    recurstyleselt.style.display = "none";
    recurlistelt.style.display = "inline";
  } else {
    if (selectelt.value == '') {
      recurstyleselt.style.display = "none";
      recurlistelt.style.display = "none";
    } else {
      recurstyleselt.style.display = "inline";
      recurlistelt.style.display = "none";
    }
  }
}

function copyfieldvalue(source, dest) {
  var sourceelt = document.getElementById(source);
  var destelt   = document.getElementById(dest);
  destelt.value = sourceelt.value;
  destelt.focus();
}
 
var datenumber = 1;
function augmentdatelist(year) {
  var prevmn = 'recurlistmonth' + datenumber;
  var prevmo = document.getElementById(prevmn);
  var month  = prevmo ? prevmo.value : 1;
  var jansel = (month == 1)  ? ' selected="selected"' : '';
  var febsel = (month == 2)  ? ' selected="selected"' : '';
  var marsel = (month == 3)  ? ' selected="selected"' : '';
  var aprsel = (month == 4)  ? ' selected="selected"' : '';
  var maysel = (month == 5)  ? ' selected="selected"' : '';
  var junsel = (month == 6)  ? ' selected="selected"' : '';
  var julsel = (month == 7)  ? ' selected="selected"' : '';
  var augsel = (month == 8)  ? ' selected="selected"' : '';
  var sepsel = (month == 9)  ? ' selected="selected"' : '';
  var octsel = (month == 10) ? ' selected="selected"' : '';
  var novsel = (month == 11) ? ' selected="selected"' : '';
  var decsel = (month == 12) ? ' selected="selected"' : '';
  var newcontent = '';
  datenumber = datenumber + 1;
  newcontent = '<tr><td><input type="text" name="recurlistyear' + datenumber + '" size="5" value="' + year + '" /></td>'
    +  '        <td><select id="recurlistmonth' + datenumber + '" name="recurlistmonth' + datenumber + '">'
    +  '              <option value="1"'  + jansel + '>Jan</option>  <option value="2"' + febsel + '>Feb</option>  <option value="3"' + marsel + '>Mar</option>'
    +  '              <option value="4"'  + aprsel + '>Apr</option>  <option value="5"' + maysel + '>May</option>  <option value="6"' + junsel + '>Jun</option>'
    +  '              <option value="7"'  + julsel + '>Jul</option>  <option value="8"' + augsel + '>Aug</option>  <option value="9"' + sepsel + '>Sep</option>'
    +  '              <option value="10"' + octsel + '>Oct</option> <option value="11"' + novsel + '>Nov</option> <option value="12"' + decsel + '>Dec</option>'
    +  '             </select></td>'
    +  '        <td><input type="text" id="recurlistmday' + datenumber + '" name="recurlistmday' + datenumber + '" size="3" /></td>';
  var elt = document.getElementById('insertmorelisteddateshere');
  insert_before_element(newcontent, elt);
}

