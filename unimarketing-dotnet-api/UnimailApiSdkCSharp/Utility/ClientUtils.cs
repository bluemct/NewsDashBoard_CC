using System;
using System.Collections.Generic;
using System.IO;
using System.ServiceModel.Syndication;
using System.Xml;
using System.Xml.Linq;
using Unimarketing.UnimailApiSdk.CSharp.Model;

namespace Unimarketing.UnimailApiSdk.CSharp.Utility
{
    public class ClientUtils
    {
        public static Account ParseAccountInfo(string xmlString)
        {
            var tr = new StringReader(xmlString);
            var xmlReader = XmlReader.Create(tr);

            SyndicationItem entry = SyndicationItem.Load(xmlReader);

            var account = new Account
                {
                    CompanyId = Convert.ToInt64(SubstringAfterLast(entry.Id, "/")),
                    CompanyName = entry.Title.Text
                };
            if (entry.Content != null)
            {
                account.CompanyDesc = entry.Content.ToString();
            }
            account.UpdateTime = entry.LastUpdatedTime.DateTime;

            foreach (SyndicationElementExtension ext in entry.ElementExtensions)
            {
                var e = ext.GetObject<XmlElement>();
                string name = ext.OuterName;

                if (name == AtomUtil.EMAIL)
                {
                    account.Email = e.InnerText;
                }
                if (name == AtomUtil.UM_TEL)
                {
                    account.Tel = e.InnerText;
                }
                if (name == AtomUtil.UM_FAX)
                {
                    account.Fax = e.InnerText;
                }
                if (name == AtomUtil.UM_POSTCODE)
                {
                    account.PostCode = e.InnerText;
                }
                if (name == AtomUtil.UM_ADDRESS)
                {
                    account.CompanyAddress = e.InnerText;
                }
                if (name == AtomUtil.UM_SERVICELIFE)
                {
                    account.StartTime = Convert.ToDateTime(e.GetAttribute("startTime"));
                    account.EndTime = Convert.ToDateTime(e.GetAttribute("endTime"));
                    account.ResidueDay = Convert.ToInt32(e.InnerText);
                }
                if (name == AtomUtil.UM_CONTACT)
                {
                    account.ContactQuota = Convert.ToInt32(e.GetAttribute("quota"));
                    account.ContactAvail = Convert.ToInt32(e.GetAttribute("avail"));
                }
                if (name == AtomUtil.UM_MAIL)
                {
                    account.MailQuota = Convert.ToInt32(e.GetAttribute("quota"));
                    account.MailAvail = Convert.ToInt32(e.GetAttribute("avail"));
                }
                if (name == AtomUtil.UM_CAPACITY)
                {
                    account.CapacityQuota = Convert.ToInt32(e.GetAttribute("quota"));
                    account.CapacityAvail = Convert.ToDouble(e.GetAttribute("avail"));
                }
            }
            return account;
        }

        public static string OrgMessageSendMail(MessageSendReq messageSendReq)
        {
            XNamespace xm = "http://www.w3.org/2005/Atom";
            XNamespace um = "http://www.unimarketing.com.cn/xmlns/";

            var root = new XElement(xm + "entry",
                                    new XAttribute(XNamespace.Xmlns + "um", um),
                                    new XElement(um + "subject", messageSendReq.Subject),
                                    new XElement(um + "from", messageSendReq.From),
                                    new XElement(um + "reply", messageSendReq.Reply),
                                    new XElement(um + "to", messageSendReq.To),
                                    new XElement("link",
                                                 new XAttribute("href",
                                                                "http://services.unimarketing.com.cn/message/" +
                                                                messageSendReq.MessageName),
                                                 new XAttribute("rel", "alternate")),
                                    new XElement("link",
                                                 new XAttribute("href",
                                                                "http://services.unimarketing.com.cn/list/" +
                                                                messageSendReq.ListName),
                                                 new XAttribute("rel", "alternate")),
                                    new XElement(xm + "content",
                                                 messageSendReq.Content,
                                                 new XAttribute("type", "html"),
                                                 new XAttribute(XNamespace.Xml + "base", um))
                );

            return root.ToString();
        }

        public static MessageSendRes ParseMessageSendMailResponse(string response)
        {
            var res = new MessageSendRes();

            TextReader tr = new StringReader(response);
            XmlReader xmlReader = XmlReader.Create(tr);

            SyndicationItem entry = SyndicationItem.Load(xmlReader);

            var links = entry.Links;
            var link = links[0];
            string path = link.Uri.ToString();

            string envelopeId = SubstringAfterLast(path, "/");
            foreach (var attr in link.AttributeExtensions)
            {
                if (attr.Key.Name == "recipient")
                {
                    res.Email = attr.Value;
                }
                if (attr.Key.Name == "status")
                {
                    res.Status = attr.Value;
                }
                if (attr.Key.Name == "warning")
                {
                    res.Warning = attr.Value;
                }
            }

            res.EnvelopeId = Convert.ToInt64(envelopeId);
            res.EnvelopeIdLink = path;

            link = links[1];
            path = link.Uri.ToString();

            res.ScheduleId = Convert.ToInt64(SubstringAfterLast(path, "/"));
            res.ScheduleIdLink = path;

            link = links[2];
            path = link.Uri.ToString();

            res.MessageId = Convert.ToInt64(SubstringAfterLast(path, "/"));
            res.MessageIdLink = path;

            return res;
        }


        public static ReportEventDeliveryDetail ParseReportEventDeliveryDetail(string response)
        {
            var res = new  ReportEventDeliveryDetail();
            res.EventDeliveries = new List<EventDelivery>();

            var doc = new XmlDocument();
            doc.LoadXml(response);
            
            string elementName = "";

            var reader = new XmlNodeReader(doc);

            while (reader.Read())
            {
                if (reader.NodeType == XmlNodeType.Element)
                {
                    elementName = reader.Name;
                    if (elementName == "entry")
                    {
                        res.EventDeliveries.Add(new EventDelivery());
                    }
                    if (elementName != "link")
                    {
                        continue;
                    }
                }
                if (reader.NodeType == XmlNodeType.EndElement)
                {
                    continue;
                }
                if (elementName == "title")
                {
                    var title = reader.Value;
                    res.StartTime = Convert.ToDateTime(title.Substring(1, 19));
                    res.FinishTime = Convert.ToDateTime(title.Substring(21, 19));
                }
                if (elementName == "openSearch:itemsPerPage")
                {
                    res.MaxResults = Convert.ToInt32(reader.Value);
                }
                if (elementName == "openSearch:startIndex")
                {
                    res.StartIndex = Convert.ToInt32(reader.Value);
                }
                if (elementName == "openSearch:totalResults")
                {
                    res.Total = Convert.ToInt32(reader.Value);
                }
                
                if (elementName == "id")
                {
                    var d = res.EventDeliveries[res.EventDeliveries.Count - 1];
                    var s = reader.Value;
                    d.Id = Convert.ToInt64(s.Substring(s.LastIndexOf("/") + 1));
                    d.IdLink = "/event/delivery/" + d.Id;
                }
                if (elementName == "um:deliveryStatus")
                {
                    var d = res.EventDeliveries[res.EventDeliveries.Count - 1];
                    d.DeliveryStatus = reader.Value;
                }
                if (elementName == "um:dsn")
                {
                    var d = res.EventDeliveries[res.EventDeliveries.Count - 1];
                    d.Dsn = reader.Value;
                }
                if (elementName == "email")
                {
                    var d = res.EventDeliveries[res.EventDeliveries.Count - 1];
                    d.Email = reader.Value;
                }
                if (elementName == "um:updated")
                {
                    var d = res.EventDeliveries[res.EventDeliveries.Count - 1];
                    d.SendTime = Convert.ToDateTime(reader.Value);
                }
                if (elementName == "link")
                {
                    var href = reader.GetAttribute("href");
                    if (href.IndexOf("/envelope/") > 0)
                    {
                        var d = res.EventDeliveries[res.EventDeliveries.Count - 1];
                        d.EnvelopeId = Convert.ToInt64(href.Substring(href.LastIndexOf("/") + 1));
                        d.EnvelopeIdLink = href;
                    }
                    if (href.IndexOf("/contact/") > 0)
                    {
                        var d = res.EventDeliveries[res.EventDeliveries.Count - 1];
                        d.ContactId = Convert.ToInt64(href.Substring(href.LastIndexOf("/") + 1));
                        d.ContactIdLink = href;
                    }
                    if (href.IndexOf("/schedule/") > 0)
                    {
                        var d = res.EventDeliveries[res.EventDeliveries.Count - 1];
                        d.ScheduleId = Convert.ToInt64(href.Substring(href.LastIndexOf("/") + 1));
                        d.ScheduleIdLink = href;
                    }
                    if (href.IndexOf("/message/") > 0)
                    {
                        var d = res.EventDeliveries[res.EventDeliveries.Count - 1];
                        d.MessageId = Convert.ToInt64(href.Substring(href.LastIndexOf("/") + 1));
                        d.MessageIdLink = href;
                    }
                }

            }

            return res;
        }

        private static string SubstringAfterLast(string s, string split)
        {
            return s.Substring(s.LastIndexOf(split) + 1, s.Length - s.LastIndexOf(split) - 1);
        }

        
    }
}